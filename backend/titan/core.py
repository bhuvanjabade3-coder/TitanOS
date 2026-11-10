"""Action registry, permission policy and approvals.

Every capability TITAN has is an *action*. The UI, the AI, voice and plugins all
call ``Registry.perform``; there is no second path to the system. Each action
may declare a gate that classifies a specific request as low / medium / high
risk. Policy then decides: run, ask the user, or refuse.

* high   -> always requires explicit approval (cannot be pre-authorised)
* medium -> requires approval unless the user set ``permissions.<category>=allow``
* low    -> runs, unless the user set ``permissions.<category>=ask``
* ``permissions.<category>=deny`` refuses the whole category

An approval stores the exact parameters; approving executes *those* parameters,
so an approval cannot be reused for a different request.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .config import Settings
from .db import Database, now
from .events import EventBus
from .notify import Notifier
from .security.risk import Risk
from .tasks import TaskConflict, TaskManager

log = logging.getLogger("titan.core")
APPROVAL_TTL = timedelta(minutes=15)
_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


class ActionError(Exception):
    """An expected, user-presentable failure."""


@dataclass
class Gate:
    risk: Risk = Risk.LOW
    reasons: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class Ctx:
    core: "Core"
    actor: str  # "user" | "ai" | "voice" | "plugin:<id>"

    @property
    def db(self) -> Database:
        return self.core.db

    @property
    def settings(self) -> Settings:
        return self.core.settings


@dataclass
class Action:
    name: str
    category: str
    description: str
    handler: Callable[[Ctx, dict], Any]
    params: dict[str, dict]
    required: list[str]
    gate: Callable[[Ctx, dict], Gate] | None
    readonly: bool
    ai: bool


def _brief(params: dict) -> dict:
    out = {}
    for k, v in params.items():
        s = v if isinstance(v, str) else json.dumps(v, default=str)
        out[k] = v if len(s) <= 300 else s[:300] + f"… ({len(s)} chars)"
    return out


class Registry:
    def __init__(self, core: "Core"):
        self.core = core
        self.actions: dict[str, Action] = {}

    def add(self, name: str, category: str, description: str, handler: Callable[[Ctx, dict], Any],
            params: dict[str, dict] | None = None, required: list[str] | None = None,
            gate: Callable[[Ctx, dict], Gate] | None = None, readonly: bool = False, ai: bool = True) -> None:
        if name in self.actions:
            raise ValueError(f"duplicate action {name}")
        self.actions[name] = Action(name, category, description, handler, params or {}, required or [], gate, readonly, ai)

    def remove_prefix(self, prefix: str) -> None:
        for k in [k for k in self.actions if k.startswith(prefix)]:
            del self.actions[k]

    def describe(self) -> list[dict]:
        return [
            {"name": a.name, "category": a.category, "description": a.description,
             "params": a.params, "required": a.required, "readonly": a.readonly}
            for a in sorted(self.actions.values(), key=lambda a: a.name)
        ]

    # --- validation --------------------------------------------------------
    @staticmethod
    def _validate(action: Action, params: Any) -> dict:
        if not isinstance(params, dict):
            raise ActionError("parameters must be an object")
        unknown = set(params) - set(action.params)
        if unknown:
            raise ActionError(f"unknown parameter(s): {', '.join(sorted(unknown))}")
        missing = [k for k in action.required if k not in params or params[k] is None]
        if missing:
            raise ActionError(f"missing required parameter(s): {', '.join(missing)}")
        for k, v in params.items():
            if v is None:
                continue
            tname = action.params[k].get("type", "")
            t = _TYPES.get(tname)
            bad_bool = isinstance(v, bool) and tname != "boolean"
            if t and (bad_bool or not isinstance(v, t)):
                raise ActionError(f"parameter `{k}` must be of type {tname}")
        return {k: v for k, v in params.items() if v is not None}

    # --- policy ------------------------------------------------------------
    def _decide(self, action: Action, gate: Gate) -> str:
        pref = self.core.db.pref(f"permissions.{action.category}")
        if pref == "deny":
            return "deny"
        if gate.risk is Risk.HIGH:
            return "ask"
        if gate.risk is Risk.MEDIUM:
            return "run" if pref == "allow" else "ask"
        return "ask" if pref == "ask" else "run"

    # --- execution ---------------------------------------------------------
    def perform(self, actor: str, name: str, params: Any = None, _approved: bool = False) -> dict:
        db = self.core.db
        action = self.actions.get(name)
        if action is None:
            return {"status": "error", "error": f"Unknown action `{name}`"}
        ctx = Ctx(self.core, actor)
        try:
            params = self._validate(action, params or {})
            if actor.startswith("plugin:") and not self.core.plugins.allowed(actor[7:], action):
                db.audit(actor, name, _brief(params), "denied:plugin-permission")
                return {"status": "denied", "error": f"Plugin lacks the `{action.category}` permission"}
            gate = action.gate(ctx, params) if action.gate else Gate()
        except ActionError as e:
            db.audit(actor, name, _brief(params if isinstance(params, dict) else {}), f"error:{e}"[:300])
            return {"status": "error", "error": str(e)}

        decision = "run" if _approved else self._decide(action, gate)
        if decision == "deny" or (not _approved and self.core.db.pref(f"permissions.{action.category}") == "deny"):
            db.audit(actor, name, _brief(params), "denied:policy")
            return {"status": "denied", "error": f"The `{action.category}` permission is set to deny"}
        if decision == "ask":
            summary = gate.summary or f"{action.description}"
            aid = db.x(
                "INSERT INTO approvals(created_at, actor, action, params, summary, risk, reasons, status) "
                "VALUES(?,?,?,?,?,?,?, 'pending')",
                (now(), actor, name, json.dumps(params), summary, gate.risk.value, json.dumps(gate.reasons)),
            )
            db.audit(actor, name, _brief(params), f"approval_required:{aid}")
            approval = self.get_approval(aid)
            self.core.bus.publish("approval", approval)
            return {"status": "approval_required", "approval_id": aid, "risk": gate.risk.value,
                    "reasons": gate.reasons, "summary": summary}
        try:
            result = action.handler(ctx, params)
        except (ActionError, TaskConflict) as e:
            db.audit(actor, name, _brief(params), f"error:{e}"[:300])
            return {"status": "error", "error": str(e)}
        except Exception as e:
            log.exception("Action %s crashed", name)
            db.audit(actor, name, _brief(params), f"crash:{type(e).__name__}")
            return {"status": "error", "error": f"Internal error in {name}: {type(e).__name__}: {e}"}
        db.audit(actor, name, _brief(params), "ok")
        return {"status": "ok", "result": result}

    # --- approvals ---------------------------------------------------------
    def _row(self, r: dict) -> dict:
        r["params"] = json.loads(r["params"])
        r["reasons"] = json.loads(r["reasons"])
        r["result"] = json.loads(r["result"]) if r["result"] else None
        return r

    def _expire(self) -> None:
        cutoff = (datetime.now(timezone.utc) - APPROVAL_TTL).isoformat(timespec="seconds")
        self.core.db.x("UPDATE approvals SET status='expired', decided_at=? WHERE status='pending' AND created_at<?", (now(), cutoff))

    def get_approval(self, aid: int) -> dict:
        self._expire()
        rows = self.core.db.q("SELECT * FROM approvals WHERE id=?", (aid,))
        if not rows:
            raise KeyError(aid)
        return self._row(rows[0])

    def approvals(self, status: str | None = "pending", limit: int = 100) -> list[dict]:
        self._expire()
        if status:
            rows = self.core.db.q("SELECT * FROM approvals WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))
        else:
            rows = self.core.db.q("SELECT * FROM approvals ORDER BY id DESC LIMIT ?", (limit,))
        return [self._row(r) for r in rows]

    def decide(self, aid: int, approve: bool) -> dict:
        db = self.core.db
        a = self.get_approval(aid)
        if a["status"] != "pending":
            raise ActionError(f"Approval {aid} is {a['status']}, not pending")
        # Claim atomically so a double-click cannot execute twice.
        claimed = db.x("UPDATE approvals SET status=?, decided_at=? WHERE id=? AND status='pending'",
                       ("approved" if approve else "denied", now(), aid))
        if not claimed:
            raise ActionError(f"Approval {aid} was already decided")
        if not approve:
            db.audit("user", "approval.deny", {"id": aid, "action": a["action"]}, "ok")
            out = {"status": "denied", "error": "The user declined this action"}
        else:
            db.audit("user", "approval.approve", {"id": aid, "action": a["action"]}, "ok")
            out = self.perform(a["actor"], a["action"], a["params"], _approved=True)
            db.x("UPDATE approvals SET status=?, result=? WHERE id=?",
                 ("executed" if out["status"] == "ok" else "failed", json.dumps(out, default=str), aid))
        final = self.get_approval(aid)
        self.core.bus.publish("approval", final)
        if a["actor"] != "user":
            ok = out["status"] == "ok"
            self.core.notifier.notify(
                "ai", f"{a['action']} {'completed' if ok else out['status']}",
                a["summary"] if ok else str(out.get("error", "")), "info" if ok else "warning")
        return {"approval": final, "outcome": out}


class Core:
    def __init__(self, settings: Settings, db: Database):
        from . import actions
        from .plugins import PluginManager

        self.settings, self.db = settings, db
        self.bus = EventBus()
        self.tasks = TaskManager(db, self.bus)
        self.notifier = Notifier(db, self.bus)
        self.registry = Registry(self)
        actions.register_all(self.registry)
        self.plugins = PluginManager(self)
        self.plugins.load_enabled()
        self._ai = None

    @property
    def ai(self):
        if self._ai is None:
            from .ai import Assistant
            self._ai = Assistant(self)
        return self._ai

    def shutdown(self) -> None:
        self.notifier.stop()
        self.tasks.shutdown()

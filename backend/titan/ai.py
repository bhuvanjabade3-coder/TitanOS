"""TITAN AI Core: Claude with tool use over the action registry.

The loop is hand-written (rather than the SDK tool runner) because TITAN must
own three things between model turns: the permission gate (a tool call can come
back as "awaiting approval"), the audit trail, and progress events to the UI.

The model never executes anything itself. Each tool call goes through
``Registry.perform`` with actor "ai", so risk gates and approvals apply exactly
as they do for any other caller, and the model is told the true outcome.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .db import now

if TYPE_CHECKING:
    from .core import Core

log = logging.getLogger("titan.ai")
MAX_RESULT_CHARS = 30_000
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM = """You are TITAN, the assistant built into TITAN OS, an AI-first desktop environment on Ubuntu. You act on the user's own computer through the tools provided.

How you work:
- For a simple request, just do it. For a multi-step request, say in one or two lines what you are going to do, then do it.
- Only the tool results tell you what happened. Report exactly that. If a tool returned an error, say what failed and why; never describe an action as done unless its tool result says it succeeded.
- Some actions pause for the user's approval. When a result says approval is required, the action has NOT run. Tell the user it is waiting for their approval in TITAN and stop working on anything that depends on it.
- If a result says the user declined or a permission is set to deny, accept that and do not look for another route to the same effect.
- Prefer the specific tool (fs_*, apps_launch, browser_*) over terminal_run. Use terminal_run when no specific tool fits.
- Before moving, renaming or deleting files, look first (fs_list / fs_search) so you act on real paths. Prefer the Trash over permanent deletion.
- You cannot see the screen. To learn what is open use windows_list or a11y_tree. If a tool reports that something is not installed or not available, tell the user what is missing rather than guessing.
- Never try to obtain, guess or bypass passwords, logins, CAPTCHAs or other security controls, and do not send messages, publish, or buy anything on the user's behalf without their explicit approval.
- Remember something long-term only via memory_save, and only for durable preferences or project context; the user approves each memory.
- Keep replies short and plain. Replies may be read aloud."""

PLAN_MODE = """

PLAN MODE: the user wants a plan, not execution. You have read-only tools. Investigate as needed, then present a short numbered plan of the actions you would take, noting which ones will need approval. Do not claim anything has been changed."""


class AIUnavailable(Exception):
    pass


class AIError(Exception):
    pass


def tool_name(action: str) -> str:
    return action.replace(".", "_")


class Assistant:
    def __init__(self, core: "Core", client: Any = None):
        self.core = core
        self._client = client

    # --- setup -------------------------------------------------------------
    def client(self) -> Any:
        if self._client is None:
            import anthropic
            key = self.core.settings.anthropic_api_key
            try:
                # With no key configured, the SDK falls back to its own credential chain.
                self._client = anthropic.Anthropic(api_key=key.get_secret_value()) if key else anthropic.Anthropic()
            except Exception as e:
                raise AIUnavailable(f"No Anthropic credentials available ({e}). Set ANTHROPIC_API_KEY for TITAN Core.")
        return self._client

    def tools(self, plan_only: bool = False) -> tuple[list[dict], dict[str, str]]:
        tools, names = [], {}
        for a in sorted(self.core.registry.actions.values(), key=lambda a: a.name):
            if not a.ai or (plan_only and not a.readonly):
                continue
            names[tool_name(a.name)] = a.name
            tools.append({"name": tool_name(a.name), "description": a.description,
                          "input_schema": {"type": "object", "properties": a.params, "required": a.required,
                                           "additionalProperties": False}})
        return tools, names

    def system(self, plan_only: bool) -> list[dict]:
        db, s = self.core.db, self.core.settings
        stable = SYSTEM + (PLAN_MODE if plan_only else "")
        context = [f"Today is {datetime.now().astimezone().strftime('%A %d %B %Y, %H:%M %Z')}.",
                   f"The user's home directory is {s.home}. File tools only work inside it."]
        personality = db.pref("ai.personality")
        if personality:
            context.append(f"The user asked for this tone: {str(personality)[:300]}")
        mems = db.q("SELECT kind, content FROM memories ORDER BY updated_at DESC LIMIT 40")
        if mems:
            context.append("Things the user approved you to remember:\n" + "\n".join(f"- ({m['kind']}) {m['content']}" for m in mems))
        # Stable instructions first with a cache breakpoint; volatile context after it.
        return [{"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": "\n".join(context)}]

    # --- conversations -----------------------------------------------------
    def _history(self, cid: int) -> list[dict]:
        out = []
        for m in self.core.db.q("SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id", (cid,)):
            text = json.loads(m["content"]).get("text", "")
            if text:
                out.append({"role": m["role"], "content": text})
        return out

    def _store(self, cid: int, role: str, payload: dict) -> None:
        self.core.db.x("INSERT INTO messages(conversation_id, role, content, created_at) VALUES(?,?,?,?)",
                       (cid, role, json.dumps(payload, default=str), now()))
        self.core.db.x("UPDATE conversations SET updated_at=? WHERE id=?", (now(), cid))

    def conversations(self) -> list[dict]:
        return self.core.db.q("SELECT * FROM conversations ORDER BY updated_at DESC, id DESC LIMIT 100")

    def conversation(self, cid: int) -> dict:
        rows = self.core.db.q("SELECT * FROM conversations WHERE id=?", (cid,))
        if not rows:
            raise KeyError(cid)
        msgs = self.core.db.q("SELECT id, role, content, created_at FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
        return {**rows[0], "messages": [{**m, "content": json.loads(m["content"])} for m in msgs]}

    def delete_conversation(self, cid: int) -> bool:
        return self.core.db.x("DELETE FROM conversations WHERE id=?", (cid,)) > 0

    # --- the loop ----------------------------------------------------------
    def _call(self, **kw: Any) -> Any:
        import anthropic
        try:
            return self.client().beta.messages.create(**kw)
        except anthropic.AuthenticationError:
            raise AIUnavailable("Anthropic rejected the API key. Check ANTHROPIC_API_KEY.")
        except anthropic.PermissionDeniedError as e:
            raise AIUnavailable(f"This API key cannot use {kw.get('model')}: {e.message}")
        except anthropic.RateLimitError:
            raise AIError("Claude is rate-limiting requests right now. Try again shortly.")
        except anthropic.APIStatusError as e:
            raise AIError(f"Claude API error {e.status_code}: {e.message}")
        except anthropic.APIConnectionError:
            raise AIError("Could not reach the Claude API. Check the network connection.")
        except TypeError as e:  # no credentials at all surfaces here in the SDK
            if "api_key" in str(e) or "auth" in str(e).lower():
                raise AIUnavailable("No Anthropic credentials available. Set ANTHROPIC_API_KEY for TITAN Core.")
            raise

    def _run_tool(self, block: Any, names: dict[str, str], actor: str) -> tuple[dict, dict]:
        action = names.get(block.name)
        args = block.input if isinstance(block.input, dict) else {}
        if action is None:
            out = {"status": "error", "error": f"No such tool: {block.name}"}
        else:
            out = self.core.registry.perform(actor, action, args)
        step = {"action": action or block.name, "input": args, "status": out["status"]}
        if out["status"] == "ok":
            text = json.dumps(out["result"], default=str)
            if len(text) > MAX_RESULT_CHARS:
                text = text[:MAX_RESULT_CHARS] + f"\n[truncated: result was {len(text)} characters]"
        elif out["status"] == "approval_required":
            step.update(approval_id=out["approval_id"], detail=out["summary"])
            text = (f"NOT EXECUTED. This action ({out['risk']} risk: {'; '.join(out['reasons']) or 'policy'}) is waiting for "
                    f"the user's approval in TITAN (approval #{out['approval_id']}). It has not run. Tell the user it "
                    "needs their approval; do not retry it and do not claim it was done.")
        else:
            step["detail"] = out.get("error", "")
            text = f"{out['status'].upper()}: {out.get('error', '')}"
        result = {"type": "tool_result", "tool_use_id": block.id, "content": text}
        if out["status"] in ("error", "denied"):
            result["is_error"] = True
        return result, step

    def chat(self, text: str, conversation_id: int | None = None, mode: str = "execute", actor: str = "ai") -> dict:
        db, s = self.core.db, self.core.settings
        text = text.strip()
        if not text:
            raise AIError("Message is empty")
        plan_only = mode == "plan"
        if conversation_id is None or not db.q("SELECT 1 FROM conversations WHERE id=?", (conversation_id,)):
            conversation_id = db.x("INSERT INTO conversations(title, created_at, updated_at) VALUES(?,?,?)",
                                   (text[:80], now(), now()))
        messages: list[dict] = self._history(conversation_id) + [{"role": "user", "content": text}]
        self._store(conversation_id, "user", {"text": text, "via": actor})
        tools, names = self.tools(plan_only)
        steps: list[dict] = []
        reply, stop = "", "error"

        def emit(kind: str, data: dict) -> None:
            self.core.bus.publish(f"ai.{kind}", {"conversation_id": conversation_id, **data})

        try:
            for _ in range(s.ai_max_steps):
                resp = self._call(model=s.ai_model, max_tokens=16000, system=self.system(plan_only), tools=tools,
                                  messages=messages, thinking={"type": "adaptive"},
                                  output_config={"effort": s.ai_effort}, betas=[FALLBACK_BETA], fallbacks="default")
                stop = resp.stop_reason
                said = "".join(b.text for b in resp.content if b.type == "text").strip()
                if said:
                    reply = said
                    emit("text", {"text": said})
                if stop == "pause_turn":
                    messages.append({"role": "assistant", "content": resp.content})
                    continue
                if stop != "tool_use":
                    if stop == "refusal":
                        why = getattr(getattr(resp, "stop_details", None), "explanation", None)
                        reply = (said + "\n\n" if said else "") + "The model declined this request." + (f" {why}" if why else "")
                    elif stop == "max_tokens":
                        reply = (said + "\n\n" if said else "") + "(The reply was cut off at the length limit.)"
                    break
                messages.append({"role": "assistant", "content": resp.content})
                results = []
                for block in resp.content:
                    if block.type != "tool_use":
                        continue
                    emit("step", {"action": names.get(block.name, block.name), "status": "running"})
                    result, step = self._run_tool(block, names, actor)
                    results.append(result)
                    steps.append(step)
                    emit("step", step)
                messages.append({"role": "user", "content": results})  # all results in one message
            else:
                stop = "step_limit"
                reply = ((reply + "\n\n") if reply else "") + (
                    f"I stopped after {s.ai_max_steps} steps without finishing. Check the steps above for what was done.")
        except (AIError, AIUnavailable) as e:
            # Persist the failure so the conversation shows what really happened.
            self._store(conversation_id, "assistant", {"text": "", "steps": steps, "error": str(e)})
            raise

        pending = [st["approval_id"] for st in steps if st["status"] == "approval_required"]
        self._store(conversation_id, "assistant", {"text": reply, "steps": steps, "stop_reason": stop})
        out = {"conversation_id": conversation_id, "reply": reply, "steps": steps,
               "pending_approvals": pending, "stop_reason": stop, "mode": mode}
        emit("done", out)
        return out

"""Notifications, preferences, tasks and system status as actions."""
from __future__ import annotations

import re

from .. import system
from ..core import ActionError, Ctx, Gate
from ..notify import CATEGORIES
from ..security.risk import Risk

KEY = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,127}$")


def g_pref(ctx: Ctx, a: dict) -> Gate:
    if not KEY.match(a["key"]):
        raise ActionError("invalid preference key")
    if a["key"].startswith("permissions."):
        if a.get("value") not in ("allow", "ask", "deny", None):
            raise ActionError("permission values are allow, ask or deny")
        if ctx.actor != "user":
            return Gate(Risk.HIGH, ["changes TITAN's own security policy"], f"Set {a['key']} = {a.get('value')}")
    return Gate()


def pref_set(ctx: Ctx, a: dict) -> dict:
    if a.get("value") is None:
        ctx.db.delete_preference(a["key"])
    else:
        ctx.db.set_preference(a["key"], a["value"])
    ctx.core.bus.publish("preference", {"key": a["key"], "value": a.get("value")})
    return {"key": a["key"], "value": a.get("value")}


def notify(ctx: Ctx, a: dict) -> dict:
    cat = a.get("category", "ai" if ctx.actor == "ai" else "app")
    if cat not in CATEGORIES:
        raise ActionError(f"category must be one of {', '.join(CATEGORIES)}")
    n = ctx.core.notifier.notify(cat, a["title"], a.get("body", ""), a.get("level", "info"))
    return n or {"muted": True}


def task_cancel(ctx: Ctx, a: dict) -> dict:
    if not ctx.core.tasks.cancel(a["id"]):
        raise ActionError(f"Task {a['id']} is not running")
    return {"cancelling": a["id"]}


def register(reg) -> None:
    S = {"type": "string"}
    reg.add("prefs.get", "preferences", "Read all user preferences", lambda c, a: c.db.get_preferences(), readonly=True)
    reg.add("prefs.set", "preferences", "Set a user preference (theme, accent colour, dock, widgets, voice, AI personality…). "
            "A null value removes it", pref_set, {"key": S, "value": {}}, ["key"], gate=g_pref)
    reg.add("notify.send", "notifications", "Show the user a notification", notify,
            {"title": S, "body": S, "category": S, "level": S}, ["title"])
    reg.add("notify.list", "notifications", "List notifications",
            lambda c, a: c.core.notifier.list(unread_only=bool(a.get("unread_only"))), {"unread_only": {"type": "boolean"}}, readonly=True, ai=False)
    reg.add("notify.read", "notifications", "Mark one (id) or all notifications as read",
            lambda c, a: {"updated": c.core.notifier.mark_read(a.get("id"))}, {"id": {"type": "integer"}}, ai=False)
    reg.add("notify.clear", "notifications", "Delete all notifications", lambda c, a: {"deleted": c.core.notifier.clear()}, ai=False)
    reg.add("tasks.list", "tasks", "List background tasks and their progress", lambda c, a: c.core.tasks.list(), readonly=True)
    reg.add("tasks.cancel", "tasks", "Cancel a running background task", task_cancel, {"id": S}, ["id"])
    reg.add("system.metrics", "system", "Current CPU, memory, disk, network, battery and temperature readings",
            lambda c, a: system.snapshot(), readonly=True)
    reg.add("system.info", "system", "Hostname, OS, kernel and architecture", lambda c, a: system.info(), readonly=True)

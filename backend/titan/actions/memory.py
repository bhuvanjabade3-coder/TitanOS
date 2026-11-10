"""Persistent memory. The assistant can only *propose* a memory; storing it
needs the user's approval. Everything is reviewable, editable, deletable and
exportable."""
from __future__ import annotations

from datetime import datetime, timezone

from ..core import ActionError, Ctx, Gate
from ..db import now
from ..security.risk import Risk

KINDS = ("preference", "project", "fact", "app", "summary")


def g_save(ctx: Ctx, a: dict) -> Gate:
    if a.get("kind", "fact") not in KINDS:
        raise ActionError(f"kind must be one of {', '.join(KINDS)}")
    if not a["content"].strip() or len(a["content"]) > 2000:
        raise ActionError("content must be 1–2000 characters")
    if ctx.actor != "user":
        return Gate(Risk.MEDIUM, ["TITAN only remembers things you approve"], f"Remember: {a['content'][:160]}")
    return Gate()


def save(ctx: Ctx, a: dict) -> dict:
    t = now()
    mid = ctx.db.x("INSERT INTO memories(kind, content, source, created_at, updated_at) VALUES(?,?,?,?,?)",
                   (a.get("kind", "fact"), a["content"].strip(), ctx.actor, t, t))
    return ctx.db.q("SELECT * FROM memories WHERE id=?", (mid,))[0]


def search(ctx: Ctx, a: dict) -> list:
    q, kind = (a.get("query") or "").strip(), a.get("kind")
    sql, params = "SELECT * FROM memories WHERE 1=1", []
    for word in q.split()[:8]:
        sql += " AND content LIKE ? ESCAPE '\\'"
        params.append("%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    return ctx.db.q(sql + " ORDER BY updated_at DESC, id DESC LIMIT 200", tuple(params))


def update(ctx: Ctx, a: dict) -> dict:
    if not a["content"].strip() or len(a["content"]) > 2000:
        raise ActionError("content must be 1–2000 characters")
    if not ctx.db.x("UPDATE memories SET content=?, updated_at=? WHERE id=?", (a["content"].strip(), now(), a["id"])):
        raise ActionError(f"No memory with id {a['id']}")
    return ctx.db.q("SELECT * FROM memories WHERE id=?", (a["id"],))[0]


def delete(ctx: Ctx, a: dict) -> dict:
    if not ctx.db.x("DELETE FROM memories WHERE id=?", (a["id"],)):
        raise ActionError(f"No memory with id {a['id']}")
    return {"deleted": a["id"]}


def export(ctx: Ctx, a: dict) -> dict:
    return {"exported_at": now(),
            "memories": ctx.db.q("SELECT * FROM memories ORDER BY id"),
            "reminders": ctx.db.q("SELECT * FROM reminders ORDER BY id"),
            "bookmarks": ctx.db.q("SELECT * FROM bookmarks ORDER BY id"),
            "preferences": ctx.db.get_preferences(),
            "conversations": ctx.db.q("SELECT * FROM conversations ORDER BY id")}


def remind(ctx: Ctx, a: dict) -> dict:
    try:
        due = datetime.fromisoformat(a["due_at"].replace("Z", "+00:00"))
    except ValueError:
        raise ActionError("due_at must be an ISO-8601 date-time, e.g. 2026-01-31T09:00:00+00:00")
    if due.tzinfo is None:
        due = due.astimezone()  # naive times are local
    due = due.astimezone(timezone.utc)
    rid = ctx.db.x("INSERT INTO reminders(text, due_at) VALUES(?,?)", (a["text"].strip()[:500], due.isoformat(timespec="seconds")))
    return ctx.db.q("SELECT * FROM reminders WHERE id=?", (rid,))[0]


def register(reg) -> None:
    S, I = {"type": "string"}, {"type": "integer"}
    reg.add("memory.save", "memory", "Propose something to remember long-term (a preference, project context or fact). "
            "The user must approve before it is stored", save, {"content": S, "kind": {"type": "string", "enum": list(KINDS)}},
            ["content"], gate=g_save)
    reg.add("memory.search", "memory", "Search stored memories (all words must match); empty query lists everything",
            search, {"query": S, "kind": S}, readonly=True)
    reg.add("memory.update", "memory", "Edit a stored memory", update, {"id": I, "content": S}, ["id", "content"], ai=False)
    reg.add("memory.delete", "memory", "Delete a stored memory", delete, {"id": I}, ["id"],
            gate=lambda c, a: Gate() if c.actor == "user" else Gate(Risk.MEDIUM, ["removes stored memory"], f"Forget memory #{a['id']}"))
    reg.add("memory.export", "memory", "Export all stored memory as JSON", export, readonly=True, ai=False)
    reg.add("reminders.add", "memory", "Create a reminder that fires a notification at due_at (ISO-8601)", remind,
            {"text": S, "due_at": S}, ["text", "due_at"])
    reg.add("reminders.list", "memory", "List reminders",
            lambda c, a: c.db.q("SELECT * FROM reminders ORDER BY done, due_at"), readonly=True)
    reg.add("reminders.delete", "memory", "Delete a reminder",
            lambda c, a: {"deleted": c.db.x("DELETE FROM reminders WHERE id=?", (a["id"],))}, {"id": I}, ["id"])

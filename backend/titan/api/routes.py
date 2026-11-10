from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .. import __version__, system
from ..auth import require_token, ws_authorized
from ..security.risk import classify

public = APIRouter()
api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])
ws_router = APIRouter()

KEY_PATTERN = r"^[a-z0-9][a-z0-9_.\-]{0,127}$"


@public.get("/health")
def health(request: Request) -> dict[str, Any]:
    return {"status": "ok", "version": __version__, "schema": request.app.state.schema_version}


@api.get("/status")
def status(request: Request) -> dict[str, Any]:
    s = request.app.state.settings
    return {
        "version": __version__,
        "ai_configured": s.ai_configured,  # boolean only; the key itself is never returned
        "system": system.info(),
    }


@api.get("/system/metrics")
def metrics() -> dict[str, Any]:
    return system.snapshot()


@api.get("/system/processes")
def processes(
    limit: int = Query(25, ge=1, le=500), sort: str = Query("memory", pattern="^(memory|cpu)$")
) -> list[dict[str, Any]]:
    return system.processes(limit, sort)


class PreferenceBody(BaseModel):
    value: Any


@api.get("/preferences")
def list_preferences(request: Request) -> dict[str, Any]:
    return request.app.state.db.get_preferences()


@api.put("/preferences/{key}")
def put_preference(key: str, body: PreferenceBody, request: Request) -> dict[str, Any]:
    import re

    if not re.fullmatch(KEY_PATTERN, key):
        raise HTTPException(422, "Invalid preference key")
    db = request.app.state.db
    if key.startswith("permissions.") and body.value not in ("allow", "ask", "deny"):
        raise HTTPException(422, "permission values are allow, ask or deny")
    db.set_preference(key, body.value)
    db.audit("user", "preference.set", {"key": key}, "ok")
    return {"key": key, "value": body.value}


@api.delete("/preferences/{key}")
def delete_preference(key: str, request: Request) -> dict[str, Any]:
    db = request.app.state.db
    if not db.delete_preference(key):
        raise HTTPException(404, "No such preference")
    db.audit("user", "preference.delete", {"key": key}, "ok")
    return {"deleted": key}


@api.get("/audit")
def audit(request: Request, limit: int = Query(100, ge=1, le=1000)) -> list[dict[str, Any]]:
    return request.app.state.db.audit_entries(limit)


class ClassifyBody(BaseModel):
    command: str = Field(max_length=8192)


@api.post("/terminal/classify")
def classify_command(body: ClassifyBody) -> dict[str, Any]:
    """Classification only. Nothing is executed by this endpoint."""
    return classify(body.command).to_dict()


# --- actions: the single entry point for everything TITAN can do -----------
class ActionBody(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


@api.get("/actions")
def list_actions(request: Request) -> list[dict[str, Any]]:
    return request.app.state.core.registry.describe()


@api.post("/actions/{name}")
def run_action(name: str, body: ActionBody, request: Request) -> dict[str, Any]:
    """Runs as the user. Returns status ok / approval_required / denied / error."""
    return request.app.state.core.registry.perform("user", name, body.params)


@api.get("/approvals")
def list_approvals(request: Request, status: str | None = "pending") -> list[dict[str, Any]]:
    return request.app.state.core.registry.approvals(status or None)


@api.post("/approvals/{aid}/{decision}")
def decide_approval(aid: int, decision: str, request: Request) -> dict[str, Any]:
    from ..core import ActionError
    if decision not in ("approve", "deny"):
        raise HTTPException(404, "decision must be approve or deny")
    try:
        return request.app.state.core.registry.decide(aid, decision == "approve")
    except KeyError:
        raise HTTPException(404, "No such approval")
    except ActionError as e:
        raise HTTPException(409, str(e))


@api.get("/tasks")
def list_tasks(request: Request) -> list[dict[str, Any]]:
    return request.app.state.core.tasks.list()


@api.get("/notifications")
def list_notifications(request: Request, unread_only: bool = False) -> list[dict[str, Any]]:
    return request.app.state.core.notifier.list(unread_only=unread_only)


# --- AI ---------------------------------------------------------------------
class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: int | None = None
    mode: str = Field("execute", pattern="^(execute|plan)$")


@api.post("/ai/chat")
def ai_chat(body: ChatBody, request: Request) -> dict[str, Any]:
    from ..ai import AIError, AIUnavailable
    try:
        return request.app.state.core.ai.chat(body.message, body.conversation_id, body.mode)
    except AIUnavailable as e:
        raise HTTPException(503, str(e))
    except AIError as e:
        raise HTTPException(502, str(e))


@api.get("/ai/conversations")
def ai_conversations(request: Request) -> list[dict[str, Any]]:
    return request.app.state.core.ai.conversations()


@api.get("/ai/conversations/{cid}")
def ai_conversation(cid: int, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.core.ai.conversation(cid)
    except KeyError:
        raise HTTPException(404, "No such conversation")


@api.delete("/ai/conversations/{cid}")
def ai_conversation_delete(cid: int, request: Request) -> dict[str, Any]:
    if not request.app.state.core.ai.delete_conversation(cid):
        raise HTTPException(404, "No such conversation")
    return {"deleted": cid}


# --- plugins ----------------------------------------------------------------
@api.get("/plugins")
def list_plugins(request: Request) -> list[dict[str, Any]]:
    return request.app.state.core.plugins.list()


@api.post("/plugins/{pid}/{op}")
def toggle_plugin(pid: str, op: str, request: Request) -> dict[str, Any]:
    from ..plugins import PluginError
    mgr = request.app.state.core.plugins
    if op not in ("enable", "disable"):
        raise HTTPException(404, "op must be enable or disable")
    try:
        return mgr.enable(pid) if op == "enable" else mgr.disable(pid)
    except PluginError as e:
        raise HTTPException(400, str(e))


# --- file preview -----------------------------------------------------------
@api.get("/files/raw")
def file_raw(path: str, request: Request):
    from fastapi.responses import FileResponse
    from ..actions.files import resolve
    from ..core import ActionError, Ctx
    try:
        p = resolve(Ctx(request.app.state.core, "user"), path, must_exist=True)
    except ActionError as e:
        raise HTTPException(403, str(e))
    if not p.is_file():
        raise HTTPException(400, "not a file")
    # nosniff + attachment-safe: never let a user file execute as a page in TITAN's origin
    return FileResponse(p, headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@ws_router.websocket("/ws/events")
async def events_stream(ws: WebSocket) -> None:
    if not await ws_authorized(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    bus = ws.app.state.core.bus
    q = bus.subscribe()
    try:
        await ws.send_json({"type": "hello", "ts": 0, "data": None})
        while True:
            await ws.send_json(await q.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(q)


@ws_router.websocket("/ws/metrics")
async def metrics_stream(ws: WebSocket) -> None:
    if not await ws_authorized(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    interval = ws.app.state.settings.metrics_interval
    try:
        while True:
            await ws.send_json(await asyncio.to_thread(system.snapshot))
            await asyncio.sleep(interval)
    except (WebSocketDisconnect, RuntimeError):
        pass

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

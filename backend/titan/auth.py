"""Local API token.

The core service will eventually execute actions on the user's machine, so even
on loopback every request must prove it comes from a TITAN client: any web page
open in a browser can otherwise reach ``127.0.0.1``. The token is generated on
first start and stored with mode 0600 in the data directory.
"""
from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

from fastapi import HTTPException, Request, WebSocket, status


def load_or_create_token(path: Path) -> str:
    if path.exists():
        token = path.read_text().strip()
        if token:
            return token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)
    os.chmod(path, 0o600)
    return token


def _presented(headers, query) -> str | None:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return query.get("token")


def token_ok(expected: str | None, headers, query) -> bool:
    if expected is None:  # auth disabled by configuration
        return True
    got = _presented(headers, query)
    return got is not None and hmac.compare_digest(got, expected)


async def require_token(request: Request) -> None:
    if not token_ok(request.app.state.api_token, request.headers, request.query_params):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid TITAN API token")


async def ws_authorized(ws: WebSocket) -> bool:
    return token_ok(ws.app.state.api_token, ws.headers, ws.query_params)

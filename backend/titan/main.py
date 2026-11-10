from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__, system
from .api.routes import api, public, ws_router
from .auth import load_or_create_token
from .config import Settings
from .db import Database
from .logging_setup import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    log = configure_logging(settings.log_dir, settings.log_level)

    db = Database(settings.db_path)
    schema_version = db.migrate()
    system.prime()

    app = FastAPI(title="TITAN Core", version=__version__)
    app.state.settings = settings
    app.state.db = db
    app.state.schema_version = schema_version
    app.state.api_token = (
        load_or_create_token(settings.token_path) if settings.require_token else None
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal error"})

    app.include_router(public)
    app.include_router(api)
    app.include_router(ws_router)
    log.info(
        "TITAN Core %s ready (schema v%s, ai_configured=%s, data_dir=%s)",
        __version__, schema_version, settings.ai_configured, settings.data_dir,
    )
    return app

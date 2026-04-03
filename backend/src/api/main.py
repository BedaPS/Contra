"""FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from urllib.parse import parse_qs, unquote

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.api.routes import router
from src.api.agent_events import router as agent_router
from src.settings_store import seed_defaults

from src.api.auth import verify_google_jwt

app = FastAPI(
    title="Contra",
    description="LLM-powered financial reconciliation pipeline.",
    version="0.1.0",
)


class JWTAuthMiddleware:
    """Pure ASGI middleware — no response buffering, SSE-safe."""

    _OPEN_PATHS = {"/api/v1/health"}

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "")
        needs_auth = (
            path.startswith("/api/v1")
            and path not in self._OPEN_PATHS
            and method != "OPTIONS"
        )

        if needs_auth:
            raw_headers = dict(scope.get("headers", []))
            auth_header = raw_headers.get(b"authorization", b"").decode()

            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]
            else:
                # EventSource cannot send headers — fall back to ?token= query param
                qs = scope.get("query_string", b"").decode()
                params = parse_qs(qs)
                token_list = params.get("token", [])
                token = unquote(token_list[0]) if token_list else ""

            if not token:
                resp = JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid Authorization header"},
                )
                await resp(scope, receive, send)
                return

            try:
                verify_google_jwt(token)
            except Exception as exc:
                logging.warning("JWT verification failed: %s", exc)
                resp = JSONResponse(
                    status_code=401,
                    content={"detail": str(exc)},
                )
                await resp(scope, receive, send)
                return

        await self.app(scope, receive, send)


app.add_middleware(JWTAuthMiddleware)

_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:4200").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(agent_router)

# Seed default settings into the database on startup
seed_defaults()

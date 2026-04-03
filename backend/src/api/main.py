"""FastAPI application entry point."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.api.agent_events import router as agent_router
from src.settings_store import seed_defaults

from fastapi import HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.api.auth import verify_google_jwt

app = FastAPI(
    title="Contra",
    description="LLM-powered financial reconciliation pipeline.",
    version="0.1.0",
)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        _OPEN_PATHS = {"/api/v1/health"}
        needs_auth = (
            request.url.path.startswith("/api/v1")
            and request.url.path not in _OPEN_PATHS
            and request.method != "OPTIONS"
        )
        if needs_auth:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing or invalid Authorization header",
                )

            token = auth_header.split(" ", 1)[1]
            verify_google_jwt(token)

        return await call_next(request)


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

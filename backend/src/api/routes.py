"""API routes — thin layer, business logic lives in agents & state_machine."""

from __future__ import annotations

from fastapi import APIRouter

from src.audit import logger as audit_log
from src.schemas.parsed_document import ParsedDocument

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/audit")
async def get_audit_log() -> list[dict]:
    """Return all audit entries (read-only view)."""
    return [e.model_dump() for e in audit_log.entries()]

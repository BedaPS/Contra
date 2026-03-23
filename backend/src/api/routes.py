"""API routes — thin layer, business logic lives in agents & state_machine."""

from __future__ import annotations

from fastapi import APIRouter

from src.audit import logger as audit_log
from src.schemas.llm_settings import LLMSettings, LLMSettingsResponse
from src.schemas.parsed_document import ParsedDocument
from src.settings_store import clear_cache, load_settings, save_settings

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/audit")
async def get_audit_log() -> list[dict]:
    """Return all audit entries (read-only view)."""
    return [e.model_dump() for e in audit_log.entries()]


# ── LLM Settings ──────────────────────────────────────────────────────────


@router.get("/settings/llm", response_model=LLMSettingsResponse)
async def get_llm_settings() -> LLMSettingsResponse:
    """Return current LLM settings (API key masked)."""
    s = load_settings()
    return LLMSettingsResponse(
        provider=s.provider,
        api_key_set=bool(s.api_key),
        model=s.model,
        base_url=s.base_url,
        temperature=s.temperature,
    )


@router.put("/settings/llm", response_model=LLMSettingsResponse)
async def update_llm_settings(body: LLMSettings) -> LLMSettingsResponse:
    """Update LLM settings. Persisted to settings.json, overrides env defaults."""
    save_settings(body)
    clear_cache()
    s = load_settings()
    return LLMSettingsResponse(
        provider=s.provider,
        api_key_set=bool(s.api_key),
        model=s.model,
        base_url=s.base_url,
        temperature=s.temperature,
    )

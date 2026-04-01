"""Settings store — database persistence with env-var defaults.

Settings are stored in the ``app_settings`` table (one row per key).
Env vars serve as fallback defaults when a key is not yet in the DB.
A thread-safe in-process cache avoids hitting the DB on every call.
"""

from __future__ import annotations

import os
from threading import Lock

from sqlalchemy import select

from src.db.engine import SessionLocal
from src.db.models import AppSettingModel
from src.schemas.llm_settings import LLMSettings

_lock = Lock()
_cache: LLMSettings | None = None

# Mapping: LLMSettings field name → environment variable name
_ENV_MAP: dict[str, str] = {
    "provider": "LLM_PROVIDER",
    "api_key": "LLM_API_KEY",
    "model": "LLM_MODEL",
    "base_url": "LLM_BASE_URL",
    "source_directory": "SOURCE_DIRECTORY",
    "work_directory": "WORK_DIRECTORY",
    "review_directory": "REVIEW_DIRECTORY",
    "output_directory": "OUTPUT_DIRECTORY",
}


def _defaults_from_env() -> dict:
    """Build default settings dict from environment variables."""
    defaults: dict = {}
    for field, env_var in _ENV_MAP.items():
        if val := os.getenv(env_var):
            defaults[field] = val
    return defaults


def load_settings() -> LLMSettings:
    """Load settings from the database, falling back to env vars then schema defaults."""
    global _cache
    with _lock:
        if _cache is not None:
            return _cache

        # Start with env var defaults
        data = _defaults_from_env()

        # Overlay with values from the database
        with SessionLocal() as session:
            rows = session.execute(select(AppSettingModel)).scalars().all()
            for row in rows:
                data[row.key] = row.value

        _cache = LLMSettings(**data)
        return _cache


def save_settings(settings: LLMSettings) -> None:
    """Persist settings to the database and refresh cache."""
    global _cache
    with _lock:
        dump = settings.model_dump()
        with SessionLocal() as session:
            for key, value in dump.items():
                existing = session.get(AppSettingModel, key)
                if existing:
                    existing.value = str(value)
                else:
                    session.add(AppSettingModel(key=key, value=str(value)))
            session.commit()
        _cache = settings


def clear_cache() -> None:
    """Force reload on next access (useful for testing)."""
    global _cache
    with _lock:
        _cache = None


def seed_defaults() -> None:
    """Write Pydantic schema defaults into the DB for any key not already present.

    Called once at app startup so the Settings page always shows values.
    Env vars take precedence over schema defaults.
    """
    defaults = LLMSettings(**_defaults_from_env()).model_dump()
    with SessionLocal() as session:
        for key, value in defaults.items():
            existing = session.get(AppSettingModel, key)
            if not existing:
                session.add(AppSettingModel(key=key, value=str(value)))
        session.commit()
    clear_cache()

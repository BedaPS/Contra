"""Settings store — JSON file persistence with env-var defaults.

Settings are loaded once and cached. The file is created on first write.
Env vars (LLM_PROVIDER, LLM_API_KEY, LLM_MODEL) serve as fallback defaults.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

from src.schemas.llm_settings import LLMSettings

_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.json"
_lock = Lock()
_cache: LLMSettings | None = None


def _defaults_from_env() -> dict:
    """Build default settings dict from environment variables."""
    defaults: dict = {}
    if val := os.getenv("LLM_PROVIDER"):
        defaults["provider"] = val
    if val := os.getenv("LLM_API_KEY"):
        defaults["api_key"] = val
    if val := os.getenv("LLM_MODEL"):
        defaults["model"] = val
    if val := os.getenv("LLM_BASE_URL"):
        defaults["base_url"] = val
    if val := os.getenv("SOURCE_DIRECTORY"):
        defaults["source_directory"] = val
    if val := os.getenv("WORK_DIRECTORY"):
        defaults["work_directory"] = val
    if val := os.getenv("REVIEW_DIRECTORY"):
        defaults["review_directory"] = val
    if val := os.getenv("OUTPUT_DIRECTORY"):
        defaults["output_directory"] = val
    return defaults


def load_settings() -> LLMSettings:
    """Load settings from disk, falling back to env vars then schema defaults."""
    global _cache
    with _lock:
        if _cache is not None:
            return _cache

        data = _defaults_from_env()

        if _SETTINGS_FILE.exists():
            try:
                file_data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
                data.update(file_data)
            except (json.JSONDecodeError, OSError):
                pass  # Corrupted file — fall back to env/defaults

        _cache = LLMSettings(**data)
        return _cache


def save_settings(settings: LLMSettings) -> None:
    """Persist settings to disk and refresh cache."""
    global _cache
    with _lock:
        _SETTINGS_FILE.write_text(
            settings.model_dump_json(indent=2),
            encoding="utf-8",
        )
        _cache = settings


def clear_cache() -> None:
    """Force reload on next access (useful for testing)."""
    global _cache
    with _lock:
        _cache = None

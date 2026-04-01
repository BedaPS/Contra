"""LLM settings schema — Pydantic v2 models for provider configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMSettings(BaseModel):
    """Runtime-configurable LLM provider settings.

    Env vars (LLM_PROVIDER, LLM_API_KEY, LLM_MODEL) serve as defaults.
    Settings persisted to disk override env values.
    """

    provider: str = Field(
        default="stub",
        description="LLM provider: gemini | openai | anthropic | local | stub",
    )
    api_key: str = Field(
        default="",
        description="Provider API key (stored locally, never logged).",
    )
    model: str = Field(
        default="gemini-2.0-flash",
        description="Model identifier (e.g. gemini-2.0-flash, gpt-4o, claude-sonnet-4-20250514).",
    )
    base_url: str = Field(
        default="",
        description="Base URL for local/self-hosted LLMs (Ollama, vLLM). Leave empty for cloud providers.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature.",
    )
    source_directory: str = Field(
        default="/app/data/source",
        description="Source directory where incoming payment proof files are placed.",
    )
    work_directory: str = Field(
        default="/app/data/work",
        description="Work directory where files are copied for processing.",
    )
    review_directory: str = Field(
        default="/app/data/review",
        description="Shared directory where spreadsheets are placed for human review.",
    )
    output_directory: str = Field(
        default="/app/data/output",
        description="Output directory where results.xlsx and accuracy.jsonl are written.",
    )


class LLMSettingsResponse(BaseModel):
    """API response — same as LLMSettings but with api_key masked."""

    provider: str
    api_key_set: bool = Field(description="Whether an API key is configured (never exposes the actual key).")
    model: str
    base_url: str
    temperature: float
    source_directory: str
    work_directory: str
    output_directory: str
    review_directory: str

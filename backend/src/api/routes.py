"""API routes — thin layer, business logic lives in agents & state_machine."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.audit import logger as audit_log
from src.graph.pipeline import get_topology
from src.schemas.llm_settings import LLMSettings, LLMSettingsResponse
from src.schemas.parsed_document import ParsedDocument
from src.settings_store import clear_cache, load_settings, save_settings

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/pipeline/topology")
async def pipeline_topology() -> dict:
    """Return the current pipeline graph topology for dynamic UI rendering."""
    return get_topology()


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
        source_directory=s.source_directory,
        work_directory=s.work_directory,
        review_directory=s.review_directory,
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
        source_directory=s.source_directory,
        work_directory=s.work_directory,
        review_directory=s.review_directory,
    )


# ── Spreadsheet Review ───────────────────────────────────────────────────


@router.get("/spreadsheet/list")
async def list_spreadsheets() -> list[dict[str, str]]:
    """List available spreadsheets in the review directory."""
    s = load_settings()
    if not s.review_directory:
        return []
    review_dir = Path(s.review_directory)
    if not review_dir.is_dir():
        return []
    files = sorted(review_dir.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"filename": f.name} for f in files]


@router.get("/spreadsheet/download/{filename}")
async def download_spreadsheet(filename: str) -> FileResponse:
    """Download a spreadsheet from the review directory."""
    s = load_settings()
    if not s.review_directory:
        raise HTTPException(status_code=400, detail="Review directory not configured.")

    # Prevent path traversal — only allow plain filenames
    safe_name = Path(filename).name
    file_path = Path(s.review_directory) / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Spreadsheet not found.")

    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/spreadsheet/upload")
async def upload_spreadsheet(file: UploadFile) -> dict[str, str]:
    """Upload a corrected spreadsheet to the review directory."""
    s = load_settings()
    if not s.review_directory:
        raise HTTPException(status_code=400, detail="Review directory not configured.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    safe_name = Path(file.filename).name
    if not safe_name.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted.")

    review_dir = Path(s.review_directory)
    review_dir.mkdir(parents=True, exist_ok=True)
    dest = review_dir / safe_name

    content = await file.read()
    dest.write_bytes(content)

    return {"path": str(dest), "filename": safe_name}

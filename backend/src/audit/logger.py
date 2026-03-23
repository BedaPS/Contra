"""Append-only audit reasoning logger.

Every agent writes a structured log entry before completing any state transition.
No PII in entries. Entries are immutable once written.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    agent: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    input_hash: str
    output_hash: str
    state_from: str
    state_to: str
    decision: str
    rationale: str
    confidence_scores: dict[str, float] = Field(default_factory=dict)


def compute_hash(payload: Any) -> str:
    """SHA-256 hex digest of the JSON-serialised payload."""
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# In-memory store — swap for a real DB in production.
# ---------------------------------------------------------------------------
_log: list[AuditEntry] = []


def append(entry: AuditEntry) -> None:
    """Append an audit entry. Append-only — no update or delete."""
    _log.append(entry)


def entries() -> list[AuditEntry]:
    """Return a shallow copy of all entries (read-only view)."""
    return list(_log)

"""Pydantic schemas for match results produced by the Auditor Agent."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MatchDecision(str, enum.Enum):
    MATCHED = "MATCHED"
    PENDING = "PENDING"
    FLAGGED = "FLAGGED"
    LOCKED = "LOCKED"
    ERROR = "ERROR"


class MatchResult(BaseModel):
    """Final output of the Auditor Agent — strict JSON, no prose."""

    match_id: str
    document_id: str
    bank_transaction_id: Optional[str] = None
    decision: MatchDecision
    amount_delta: float = Field(
        description="bank_amount − email_amount. Must be 0.00 for MATCHED.",
    )
    name_similarity: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Levenshtein similarity score (0.0–1.0). Null when Bank Ref ID match.",
    )
    bank_reference_id_match: bool = Field(
        default=False,
        description="True when match was made via Bank Reference ID (100% precedence).",
    )
    temporal_delta_days: Optional[int] = Field(
        default=None, ge=0,
        description="Absolute days between email date and bank date.",
    )
    rationale: str = Field(
        description="Plain-English explanation of the match decision.",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

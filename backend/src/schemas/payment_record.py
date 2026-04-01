"""Payment record Pydantic schemas — API serialisation for doc processing pipeline."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PaymentRecordCreate(BaseModel):
    """Internal model — written after LangGraph validation node."""

    run_record_id: str
    batch_id: str
    # 14 extracted fields (all nullable)
    customer_name: str | None = None
    account_number: str | None = None
    payee: str | None = None
    payment_id: str | None = None
    payment_method: str | None = None
    payment_date: str | None = None
    invoice_number: str | None = None
    reference_doc_number: str | None = None
    amount_paid: float | None = None
    currency: str | None = None
    deductions: float | None = None
    deduction_type: str | None = None
    notes: str | None = None
    page_number: int | None = None
    overall_confidence: float = 0.0  # Mean of confidence_scores; backing field for filters
    # Validation
    validation_status: str  # 'Valid' | 'Review Required' | 'Extraction Failed'
    confidence_scores: dict[str, float]
    llm_provider: str
    llm_model: str
    source_filename: str
    doc_type: str


class PaymentRecordResponse(PaymentRecordCreate):
    """API response — includes DB id and created_at."""

    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

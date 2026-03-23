"""Auditor Agent — matches parsed documents against bank statements.

Constitution mandates injected into the system prompt at initialisation:
  "You are the Auditor Agent of Contra. You operate under the Contra
   Constitution. Your primary directive is precision. You are forbidden from
   assuming a match. If a Bank Reference ID is present, it takes 100%
   precedence over Name Similarity. Do not output anything except the
   final Match JSON."
"""

from __future__ import annotations

import uuid
from datetime import date

from Levenshtein import ratio as levenshtein_ratio

from src.audit import logger as audit_log
from src.audit.logger import AuditEntry, compute_hash
from src.schemas.match_result import MatchDecision, MatchResult
from src.schemas.parsed_document import ParsedDocument

# Constitution thresholds
NAME_SIMILARITY_THRESHOLD = 0.90
TEMPORAL_WINDOW_DAYS = 7

SYSTEM_PROMPT = (
    "You are the Auditor Agent of Contra. You operate under the Contra "
    "Constitution. Your primary directive is precision. You are forbidden "
    "from assuming a match. If a Bank Reference ID is present, it takes "
    "100% precedence over Name Similarity. Do not output anything except "
    "the final Match JSON."
)


class BankTransaction:
    """Lightweight representation of a bank statement line."""

    __slots__ = ("transaction_id", "account_name", "amount", "date", "reference_id")

    def __init__(
        self,
        transaction_id: str,
        account_name: str,
        amount: float,
        date: date,
        reference_id: str | None = None,
    ) -> None:
        self.transaction_id = transaction_id
        self.account_name = account_name
        self.amount = amount
        self.date = date
        self.reference_id = reference_id


def match(doc: ParsedDocument, candidates: list[BankTransaction]) -> MatchResult:
    """Attempt to match *doc* against bank transaction *candidates*.

    Returns a MatchResult with the decision and rationale.
    """
    email_amount = float(doc.amount.value) if doc.amount.value else 0.0
    email_date = _parse_date(doc.payment_date.value)
    email_ref = doc.bank_reference_id.value if doc.bank_reference_id else None

    viable: list[BankTransaction] = []

    for txn in candidates:
        # --- Temporal window check (7 calendar days inclusive) ---
        if email_date is not None:
            delta = abs((txn.date - email_date).days)
            if delta > TEMPORAL_WINDOW_DAYS:
                continue
        # --- Zero variance check ---
        if txn.amount - email_amount != 0.0:
            continue
        viable.append(txn)

    # Duplicate Lock Rule: two+ identical candidates → LOCKED
    if len(viable) > 1:
        return _locked_result(doc, viable)

    if not viable:
        return _pending_result(doc, email_amount)

    txn = viable[0]
    delta_days = abs((txn.date - email_date).days) if email_date else None

    # --- Bank Reference ID supremacy ---
    if email_ref and txn.reference_id and email_ref == txn.reference_id:
        result = MatchResult(
            match_id=str(uuid.uuid4()),
            document_id=doc.document_id,
            bank_transaction_id=txn.transaction_id,
            decision=MatchDecision.MATCHED,
            amount_delta=0.0,
            bank_reference_id_match=True,
            temporal_delta_days=delta_days,
            rationale=f"Bank Ref ID '{email_ref}' matched exactly.",
        )
        _log_match(doc, result)
        return result

    # --- Name similarity ---
    score = levenshtein_ratio(
        (doc.account_name.value or "").lower(),
        txn.account_name.lower(),
    )
    if score < NAME_SIMILARITY_THRESHOLD:
        result = MatchResult(
            match_id=str(uuid.uuid4()),
            document_id=doc.document_id,
            bank_transaction_id=txn.transaction_id,
            decision=MatchDecision.FLAGGED,
            amount_delta=0.0,
            name_similarity=round(score, 4),
            temporal_delta_days=delta_days,
            rationale=f"Name similarity {score:.4f} below threshold {NAME_SIMILARITY_THRESHOLD}.",
        )
        _log_match(doc, result)
        return result

    result = MatchResult(
        match_id=str(uuid.uuid4()),
        document_id=doc.document_id,
        bank_transaction_id=txn.transaction_id,
        decision=MatchDecision.MATCHED,
        amount_delta=0.0,
        name_similarity=round(score, 4),
        temporal_delta_days=delta_days,
        rationale=f"Amount $0.00 delta, name similarity {score:.4f}, within {delta_days}-day window.",
    )
    _log_match(doc, result)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    from datetime import datetime as dt
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _locked_result(doc: ParsedDocument, viable: list[BankTransaction]) -> MatchResult:
    ids = ", ".join(t.transaction_id for t in viable)
    result = MatchResult(
        match_id=str(uuid.uuid4()),
        document_id=doc.document_id,
        decision=MatchDecision.LOCKED,
        amount_delta=0.0,
        rationale=f"Duplicate candidates detected ({ids}). Both LOCKED — human review required.",
    )
    _log_match(doc, result)
    return result


def _pending_result(doc: ParsedDocument, email_amount: float) -> MatchResult:
    result = MatchResult(
        match_id=str(uuid.uuid4()),
        document_id=doc.document_id,
        decision=MatchDecision.PENDING,
        amount_delta=email_amount,
        rationale="No matching bank transaction found. Status: Pending.",
    )
    _log_match(doc, result)
    return result


def _log_match(doc: ParsedDocument, result: MatchResult) -> None:
    entry = AuditEntry(
        agent="auditor_agent",
        input_hash=compute_hash(doc.model_dump()),
        output_hash=compute_hash(result.model_dump()),
        state_from=doc.state.value,
        state_to=result.decision.value,
        decision=result.decision.value,
        rationale=result.rationale,
        confidence_scores={"name_similarity": result.name_similarity or 0.0},
    )
    audit_log.append(entry)

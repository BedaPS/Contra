"""Run/batch schemas — API serialisation for doc processing pipeline."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RunStartedResponse(BaseModel):
    batch_id: str
    total_files: int
    status: str


class RunRecordSummary(BaseModel):
    record_id: str
    source_filename: str
    guid_filename: str
    status: str
    record_count: int
    started_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class BatchRunSummary(BaseModel):
    batch_id: str
    triggered_at: datetime
    completed_at: datetime | None = None
    total_files: int
    total_records: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class BatchRunDetail(BatchRunSummary):
    run_records: list[RunRecordSummary] = []

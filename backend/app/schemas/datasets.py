from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .base import ORMModel


class DatasetOut(ORMModel):
    id: str
    name: str
    filename: str
    file_sha256: str
    storage_path: str | None
    status: str
    row_count: int
    parsed_count: int
    failed_count: int
    analyzed_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class StoredCsvFileOut(BaseModel):
    filename: str
    storage_path: str
    size_bytes: int
    modified_at: datetime
    dataset_id: str | None = None
    dataset_name: str | None = None
    status: str | None = None
    row_count: int | None = None
    file_sha256: str | None = None


class AnalyzeRequest(BaseModel):
    use_llm: bool = True
    llm_scope: Literal["suspicious", "all"] = "suspicious"
    force: bool = False


class BatchAnalyzeRequest(AnalyzeRequest):
    dataset_ids: list[str] = Field(min_length=1, max_length=100)
    skip_running: bool = True


class JobOut(ORMModel):
    id: str
    dataset_id: str
    status: str
    phase: str
    use_llm: bool
    llm_scope: str
    force: bool
    cancel_requested: bool
    total: int
    processed: int
    succeeded: int
    failed: int
    current_event_id: str | None
    last_heartbeat_at: datetime | None
    last_error_at: datetime | None
    error_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class BatchAnalyzeItem(BaseModel):
    dataset_id: str
    status: Literal["queued", "skipped", "not_found", "conflict"]
    job: JobOut | None = None
    message: str | None = None


class BatchAnalyzeResult(BaseModel):
    requested: int
    queued: int
    skipped: int
    items: list[BatchAnalyzeItem]


class DatasetCompareResult(BaseModel):
    baseline_dataset_id: str
    candidate_dataset_id: str
    counts: dict[str, int]
    risk: dict[str, float]
    new_hosts: list[str]
    new_paths: list[str]
    new_attack_types: list[str]
    repeated_payload_hashes: list[str]

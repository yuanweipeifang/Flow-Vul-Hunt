from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .base import ORMModel


class FindingOut(ORMModel):
    id: str
    detector_type: str
    detector_name: str
    attack_type: str
    severity: str
    confidence: float
    matched_fragment: str | None
    evidence: dict[str, Any]
    created_at: datetime


class LLMAnalysisOut(ORMModel):
    id: str
    agent_name: str
    provider: str
    model_name: str
    prompt_version: str
    structured_result: dict[str, Any] | None
    token_usage: dict[str, Any]
    latency_ms: int | None
    status: str
    error_message: str | None
    created_at: datetime


class EventSummary(ORMModel):
    id: str
    dataset_id: str
    row_number: int
    protocol: str
    http_method: str | None
    host: str | None
    path: str | None
    payload_length: int
    is_binary: bool
    parse_status: str
    verdict: str
    risk_score: float
    created_at: datetime


class EventDetail(EventSummary):
    raw_payload: str
    decoded_payload: str
    payload_hash: str
    query: str | None
    headers: dict[str, Any]
    body: str | None
    content_type: str | None
    entropy: float
    printable_ratio: float
    encoded_segment_count: int
    parse_error: str | None
    findings: list[FindingOut]
    llm_analyses: list[LLMAnalysisOut]


class ExtractedFeatureOut(BaseModel):
    id: str | None = None
    event_id: str
    feature_version: str = "1.0"
    features: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginatedEvents(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[EventSummary]

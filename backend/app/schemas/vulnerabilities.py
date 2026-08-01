from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .base import ORMModel
from .events import EventSummary


class VulnerabilityCandidateUpdate(BaseModel):
    status: Literal[
        "candidate",
        "needs_review",
        "triaged",
        "validated",
        "confirmed",
        "fixed",
        "false_positive",
        "rejected",
    ] | None = None
    reviewer: str | None = Field(default=None, max_length=128)
    comment: str | None = Field(default=None, max_length=4000)


class VulnerabilityCandidateOut(ORMModel):
    id: str
    dataset_id: str
    event_id: str
    candidate_type: str
    title: str
    target_component: str | None
    severity: str
    confidence: float
    status: str
    signature: str
    evidence: dict[str, Any]
    impact: str
    validation_summary: dict[str, Any]
    reviewer: str | None
    comment: str | None
    created_at: datetime
    updated_at: datetime


class VulnerabilityGroupOut(BaseModel):
    group_key: str
    dataset_id: str | None
    candidate_type: str
    target_component: str | None
    count: int
    max_confidence: float
    max_severity: str
    statuses: dict[str, int]
    sample_ids: list[str]


class VulnerabilityValidateRequest(BaseModel):
    target_id: str
    method: Literal["GET", "HEAD", "OPTIONS"] = "HEAD"
    path: str | None = Field(default=None, max_length=512)
    probe: Literal["none", "safe_marker"] = "none"
    requested_by: str | None = Field(default=None, max_length=128)

    @field_validator("path")
    @classmethod
    def normalize_validation_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip() or "/"
        return value if value.startswith("/") else f"/{value}"


class ValidationResultOut(ORMModel):
    id: str
    run_id: str
    target_id: str
    method: str
    url: str
    status: str
    conclusion: str
    request_summary: dict[str, Any]
    response_summary: dict[str, Any]
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class ValidationRunOut(ORMModel):
    id: str
    vulnerability_id: str
    target_id: str
    status: str
    requested_by: str | None
    request_options: dict[str, Any]
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    results: list[ValidationResultOut] = []


class VulnerabilityAnalysisOut(BaseModel):
    vulnerability: VulnerabilityCandidateOut
    analysis_summary: str
    confidence_factors: list[str]
    false_positive_risks: list[str]
    validation_focus: list[str]
    related_event: EventSummary
    validation_history: list[ValidationRunOut]

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import ORMModel


class IncidentEventOut(ORMModel):
    event_id: str
    relation_type: str
    evidence: dict[str, Any]
    sort_order: int


class IncidentUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved", "closed"] | None = None
    assignee: str | None = Field(default=None, max_length=128)
    resolution: str | None = Field(default=None, max_length=10000)


class IncidentOut(ORMModel):
    id: str
    dataset_id: str
    title: str
    incident_type: str
    summary: str
    risk_score: float
    severity: str
    status: str
    assignee: str | None
    resolution: str | None
    closed_at: datetime | None
    is_simulated: bool
    created_at: datetime
    updated_at: datetime
    event_links: list[IncidentEventOut] = []


class ReportGenerateRequest(BaseModel):
    use_llm: bool = True


class IncidentReportOut(ORMModel):
    id: str
    incident_id: str
    generator: str
    model_name: str | None
    content: dict[str, Any]
    status: str
    error_message: str | None
    created_at: datetime

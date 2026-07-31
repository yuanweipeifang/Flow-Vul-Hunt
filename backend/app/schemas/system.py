from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import ORMModel


class HealthOut(BaseModel):
    status: str
    database: str
    migrations: dict[str, Any]
    database_writable: bool
    recent_task_errors: int
    llm_configured: bool
    llm_enabled: bool
    providers: list[dict[str, Any]]
    agent_routes: dict[str, list[str]]


class ProviderTestRequest(BaseModel):
    providers: list[Literal["deepseek", "bailian", "zhipu"]] | None = None


class ProviderTestResult(BaseModel):
    provider: str
    configured: bool
    success: bool
    model: str
    latency_ms: int | None = None
    token_usage: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ErrorOut(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class AuditLogOut(ORMModel):
    id: str
    action: str
    actor: str
    role: str
    request_id: str | None
    resource_type: str
    resource_id: str | None
    details: dict[str, Any]
    created_at: datetime


class SystemMetricsOut(BaseModel):
    datasets: int
    events: int
    running_jobs: int
    failed_jobs: int
    llm_success: int
    llm_failure: int
    validation_runs_by_status: dict[str, int]

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DatasetOut(ORMModel):
    id: str
    name: str
    filename: str
    file_sha256: str
    status: str
    row_count: int
    parsed_count: int
    failed_count: int
    analyzed_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


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


class AnnotationCreate(BaseModel):
    label: Literal["malicious", "benign", "suspicious", "unknown"]
    attack_type: str | None = Field(default=None, max_length=64)
    severity: Literal["info", "low", "medium", "high", "critical"] | None = None
    review_status: Literal["confirmed", "rejected", "needs_review"] = "confirmed"
    reviewer: str | None = Field(default=None, max_length=128)
    comment: str | None = Field(default=None, max_length=4000)


class AnnotationOut(ORMModel):
    id: str
    label: str
    attack_type: str | None
    severity: str | None
    review_status: str
    reviewer: str | None
    comment: str | None
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
    annotations: list[AnnotationOut]


class AnalyzeRequest(BaseModel):
    use_llm: bool = True
    llm_scope: Literal["suspicious", "all"] = "suspicious"
    force: bool = False


class JobOut(ORMModel):
    id: str
    dataset_id: str
    status: str
    use_llm: bool
    llm_scope: str
    force: bool
    cancel_requested: bool
    total: int
    processed: int
    succeeded: int
    failed: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


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


class HuntRequest(BaseModel):
    dataset_id: str | None = None
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=50, ge=1, le=200)
    use_llm: bool = True


class HuntResult(BaseModel):
    interpreted_filters: dict[str, Any]
    events: list[EventSummary]
    summary: str | None = None
    llm_used: bool = False
    warning: str | None = None


class DashboardOverview(BaseModel):
    totals: dict[str, int]
    datasets_by_status: dict[str, int]
    events_by_verdict: dict[str, int]
    incidents_by_severity: dict[str, int]
    incidents_by_status: dict[str, int]
    top_attack_types: dict[str, int]
    risk: dict[str, float]


class RuleOut(BaseModel):
    rule_id: str
    attack_type: str
    severity: str
    confidence: float
    description: str
    detector_type: str
    enabled: bool = True


class CustomRuleCreate(BaseModel):
    rule_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    attack_type: str = Field(min_length=1, max_length=64)
    severity: Literal["info", "low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    pattern: str = Field(min_length=1, max_length=4000)
    enabled: bool = True


class CustomRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    attack_type: str | None = Field(default=None, min_length=1, max_length=64)
    severity: Literal["info", "low", "medium", "high", "critical"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    pattern: str | None = Field(default=None, min_length=1, max_length=4000)
    enabled: bool | None = None


class CustomRuleOut(ORMModel):
    id: str
    rule_id: str
    name: str
    description: str
    attack_type: str
    severity: str
    confidence: float
    pattern: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class RuleTestRequest(BaseModel):
    payload: str = Field(min_length=1, max_length=100_000)


class RuleMatchOut(BaseModel):
    detector_name: str
    detector_type: str
    attack_type: str
    severity: str
    confidence: float
    matched_fragment: str | None
    evidence: dict[str, Any]


class RuleTestResult(BaseModel):
    parse_status: str
    is_binary: bool
    matches: list[RuleMatchOut]


class PayloadInspectRequest(BaseModel):
    payload: str = Field(min_length=1, max_length=100_000)


class PayloadInspectResult(BaseModel):
    parsed: dict[str, Any]
    decoded_variants: dict[str, str | None]
    warnings: list[str] = Field(default_factory=list)


class DatasetCompareResult(BaseModel):
    baseline_dataset_id: str
    candidate_dataset_id: str
    counts: dict[str, int]
    risk: dict[str, float]
    new_hosts: list[str]
    new_paths: list[str]
    new_attack_types: list[str]
    repeated_payload_hashes: list[str]


class AuthorizedTargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scheme: Literal["http", "https"]
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    path_scope: str = Field(default="/", min_length=1, max_length=512)
    enabled: bool = True
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("path_scope")
    @classmethod
    def normalize_path_scope(cls, value: str) -> str:
        value = value.strip() or "/"
        return value if value.startswith("/") else f"/{value}"


class AuthorizedTargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    scheme: Literal["http", "https"] | None = None
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    path_scope: str | None = Field(default=None, min_length=1, max_length=512)
    enabled: bool | None = None
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("host")
    @classmethod
    def normalize_optional_host(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("path_scope")
    @classmethod
    def normalize_optional_path_scope(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip() or "/"
        return value if value.startswith("/") else f"/{value}"


class AuthorizedTargetOut(ORMModel):
    id: str
    name: str
    scheme: str
    host: str
    port: int | None
    path_scope: str
    enabled: bool
    note: str | None
    created_at: datetime
    updated_at: datetime


class ExtractedFeatureOut(BaseModel):
    id: str | None = None
    event_id: str
    feature_version: str = "1.0"
    features: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VulnerabilityCandidateUpdate(BaseModel):
    status: Literal["candidate", "needs_review", "validated", "confirmed", "rejected"] | None = None
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


class VulnerabilityValidateRequest(BaseModel):
    target_id: str
    method: Literal["GET", "HEAD", "OPTIONS"] = "HEAD"
    path: str | None = Field(default=None, max_length=512)
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


class PaginatedEvents(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[EventSummary]


class HealthOut(BaseModel):
    status: str
    database: str
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

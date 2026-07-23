from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ALLOWED_ATTACK_TYPES = {
    "command_injection",
    "sql_injection",
    "path_traversal",
    "expression_injection",
    "jndi_injection",
    "webshell_activity",
    "sensitive_endpoint_probe",
    "ssrf",
    "cross_site_scripting",
    "deserialization",
    "file_upload",
    "authentication_attack",
    "protocol_anomaly",
    "unknown",
}


class EvidenceItem(BaseModel):
    field: str = Field(max_length=64)
    fragment: str = Field(max_length=1000)
    explanation: str = Field(max_length=1000)


class PayloadAnalysisResult(BaseModel):
    verdict: Literal["malicious", "benign", "suspicious", "unknown"]
    attack_types: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0, le=1)
    target_component: str | None = Field(default=None, max_length=256)
    intent: str = Field(max_length=1000)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=12)
    possible_impact: list[str] = Field(default_factory=list, max_length=10)
    uncertainties: list[str] = Field(default_factory=list, max_length=10)
    needs_human_review: bool

    @field_validator("attack_types")
    @classmethod
    def validate_attack_types(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values]
        invalid = sorted(set(normalized) - ALLOWED_ATTACK_TYPES)
        if invalid:
            raise ValueError(f"unsupported attack types: {', '.join(invalid)}")
        return normalized


class VerificationResult(BaseModel):
    accepted: bool
    corrected_verdict: Literal["malicious", "benign", "suspicious", "unknown"]
    corrected_confidence: float = Field(ge=0, le=1)
    supported_evidence_indexes: list[int] = Field(default_factory=list)
    rejected_claims: list[str] = Field(default_factory=list, max_length=10)
    explanation: str = Field(max_length=2000)
    needs_human_review: bool


class HuntFilters(BaseModel):
    verdict: Literal["malicious", "benign", "suspicious", "unknown", "unreviewed"] | None = None
    min_risk_score: float | None = Field(default=None, ge=0, le=100)
    attack_type: str | None = Field(default=None, max_length=64)
    host_contains: str | None = Field(default=None, max_length=255)
    path_contains: str | None = Field(default=None, max_length=255)
    method: str | None = Field(default=None, max_length=16)
    payload_contains: str | None = Field(default=None, max_length=255)
    is_binary: bool | None = None


class IncidentReportContent(BaseModel):
    executive_summary: str = Field(max_length=3000)
    technical_summary: str = Field(max_length=6000)
    evidence_event_ids: list[str] = Field(default_factory=list, max_length=100)
    attack_types: list[str] = Field(default_factory=list, max_length=20)
    vulnerability_candidates: list[dict] = Field(default_factory=list, max_length=50)
    validation_results: list[dict] = Field(default_factory=list, max_length=50)
    recommended_actions: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class ConnectionTestResult(BaseModel):
    status: Literal["ok"]

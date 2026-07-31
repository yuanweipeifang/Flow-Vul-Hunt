from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import ORMModel


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


class RuleDryRunRequest(BaseModel):
    rule: CustomRuleCreate
    dataset_id: str | None = None
    limit: int = Field(default=500, ge=1, le=5000)


class RuleDryRunSample(BaseModel):
    event_id: str
    dataset_id: str
    row_number: int
    host: str | None
    path: str | None
    matched_fragment: str | None


class RuleDryRunResult(BaseModel):
    tested: int
    matched: int
    match_rate: float
    samples: list[RuleDryRunSample]

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import ORMModel


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    dataset_id: str | None = None
    auto_execute: bool = False
    confirmed_tool_call_ids: list[str] = Field(default_factory=list, max_length=20)
    max_steps: int | None = Field(default=None, ge=1, le=20)


class AgentToolCallOut(BaseModel):
    id: str
    name: str
    risk_level: Literal["read_only", "write_review", "high_risk"]
    arguments: dict[str, Any]
    status: Literal["planned", "executed", "blocked", "failed"]
    requires_confirmation: bool = False
    result: Any | None = None
    error: str | None = None


class AgentMessageOut(BaseModel):
    id: str
    agent_name: str
    role: str
    task: str
    input_summary: dict[str, Any]
    output: dict[str, Any]
    depends_on: list[str] = []
    evidence_refs: list[dict[str, Any]] = []
    confidence: float = 0.0
    llm_used: bool = False
    status: str = "completed"
    error: str | None = None
    created_at: datetime | None = None


class AgentRunOut(BaseModel):
    id: str
    session_id: str
    collaboration_mode: str
    runtime: str
    planner_used: str
    status: str
    max_parallelism: int
    llm_used: bool
    consensus: dict[str, Any]
    evidence_gaps: list[str]
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    messages: list[AgentMessageOut] = []


class AgentChatResult(BaseModel):
    session_id: str
    runtime: str
    hermes_isolated: bool
    plan: list[str]
    tool_calls: list[AgentToolCallOut]
    answer: str
    requires_confirmation: bool = False
    warning: str | None = None
    planner_used: str = "local"
    collaboration_mode: str = "single_planner"
    agents: list[AgentMessageOut] = []
    consensus: dict[str, Any] = Field(default_factory=dict)
    evidence_gaps: list[str] = Field(default_factory=list)
    llm_used: bool = False


class AgentStatusOut(BaseModel):
    enabled: bool
    runtime: str
    hermes_available: bool
    hermes_python_available: bool = False
    hermes_cli_available: bool = False
    hermes_config_dir: str
    hermes_plugin_dir: str
    hermes_isolated: bool
    allowed_tools: list[str]
    require_confirmation: bool
    collaboration_enabled: bool = False
    collaboration_mode: str = "single_planner"
    agent_roles: list[str] = []
    max_parallelism: int = 1
    require_verifier: bool = True


class AgentSessionOut(ORMModel):
    id: str
    actor: str
    role: str
    message: str
    dataset_id: str | None
    runtime: str
    planner_used: str
    status: str
    plan: list[str]
    answer: str
    warning: str | None
    requires_confirmation: bool
    created_at: datetime
    updated_at: datetime
    tool_calls: list[AgentToolCallOut] = []
    runs: list[AgentRunOut] = []


class AgentTraceOut(BaseModel):
    session: AgentSessionOut
    runs: list[AgentRunOut]


class AgentConfirmRequest(BaseModel):
    tool_call_ids: list[str] = Field(min_length=1, max_length=20)

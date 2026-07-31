from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
<<<<<<< Updated upstream

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    events: Mapped[list[PayloadEvent]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class PayloadEvent(Base):
    __tablename__ = "payload_events"
    __table_args__ = (
        UniqueConstraint("dataset_id", "row_number", name="uq_dataset_row"),
        Index("ix_event_dataset_risk", "dataset_id", "risk_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    raw_payload: Mapped[str] = mapped_column(Text)
    decoded_payload: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    protocol: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    http_method: Mapped[str | None] = mapped_column(String(16), index=True)
    host: Mapped[str | None] = mapped_column(String(512), index=True)
    path: Mapped[str | None] = mapped_column(Text)
    query: Mapped[str | None] = mapped_column(Text)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    body: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(255))
    payload_length: Mapped[int] = mapped_column(Integer, default=0)
    entropy: Mapped[float] = mapped_column(Float, default=0.0)
    printable_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    encoded_segment_count: Mapped[int] = mapped_column(Integer, default=0)
    is_binary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    parse_error: Mapped[str | None] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(32), default="unreviewed", index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    dataset: Mapped[Dataset] = relationship(back_populates="events")
=======

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    events: Mapped[list[PayloadEvent]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class PayloadEvent(Base):
    __tablename__ = "payload_events"
    __table_args__ = (
        UniqueConstraint("dataset_id", "row_number", name="uq_dataset_row"),
        Index("ix_event_dataset_risk", "dataset_id", "risk_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    raw_payload: Mapped[str] = mapped_column(Text)
    decoded_payload: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    protocol: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    http_method: Mapped[str | None] = mapped_column(String(16), index=True)
    host: Mapped[str | None] = mapped_column(String(512), index=True)
    path: Mapped[str | None] = mapped_column(Text)
    query: Mapped[str | None] = mapped_column(Text)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    body: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(255))
    payload_length: Mapped[int] = mapped_column(Integer, default=0)
    entropy: Mapped[float] = mapped_column(Float, default=0.0)
    printable_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    encoded_segment_count: Mapped[int] = mapped_column(Integer, default=0)
    is_binary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    parse_error: Mapped[str | None] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(32), default="unreviewed", index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    dataset: Mapped[Dataset] = relationship(back_populates="events")
>>>>>>> Stashed changes
    findings: Mapped[list[DetectionFinding]] = relationship(back_populates="event", cascade="all, delete-orphan")
    llm_analyses: Mapped[list[LLMAnalysis]] = relationship(back_populates="event", cascade="all, delete-orphan")
    annotations: Mapped[list[Annotation]] = relationship(back_populates="event", cascade="all, delete-orphan")
    extracted_feature: Mapped[ExtractedFeature | None] = relationship(
        back_populates="event", cascade="all, delete-orphan", uselist=False
    )
    vulnerability_candidates: Mapped[list[VulnerabilityCandidate]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class DetectionFinding(Base):
    __tablename__ = "detection_findings"
    __table_args__ = (Index("ix_finding_event_detector", "event_id", "detector_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("payload_events.id", ondelete="CASCADE"), index=True)
    detector_type: Mapped[str] = mapped_column(String(32), index=True)
    detector_name: Mapped[str] = mapped_column(String(128))
    attack_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    matched_fragment: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event: Mapped[PayloadEvent] = relationship(back_populates="findings")


class CustomRule(Base):
    __tablename__ = "custom_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    attack_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    pattern: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuthorizedTarget(Base):
    __tablename__ = "authorized_targets"
    __table_args__ = (
        UniqueConstraint("scheme", "host", "port", "path_scope", name="uq_authorized_target_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    scheme: Mapped[str] = mapped_column(String(8), index=True)
    host: Mapped[str] = mapped_column(String(255), index=True)
    port: Mapped[int | None] = mapped_column(Integer)
    path_scope: Mapped[str] = mapped_column(String(512), default="/")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    validation_runs: Mapped[list[ValidationRun]] = relationship(back_populates="target")


class ExtractedFeature(Base):
    __tablename__ = "extracted_features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("payload_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    feature_version: Mapped[str] = mapped_column(String(32), default="1.0")
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    event: Mapped[PayloadEvent] = relationship(back_populates="extracted_feature")


class VulnerabilityCandidate(Base):
    __tablename__ = "vulnerability_candidates"
    __table_args__ = (
        UniqueConstraint("event_id", "candidate_type", "signature", name="uq_vuln_candidate_signature"),
        Index("ix_vuln_dataset_status", "dataset_id", "status"),
        Index("ix_vuln_dataset_type", "dataset_id", "candidate_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("payload_events.id", ondelete="CASCADE"), index=True)
    candidate_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    target_component: Mapped[str | None] = mapped_column(String(512))
    severity: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    signature: Mapped[str] = mapped_column(String(64), index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    impact: Mapped[str] = mapped_column(Text)
    validation_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewer: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    event: Mapped[PayloadEvent] = relationship(back_populates="vulnerability_candidates")
    validation_runs: Mapped[list[ValidationRun]] = relationship(
        back_populates="vulnerability", cascade="all, delete-orphan"
    )


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    vulnerability_id: Mapped[str] = mapped_column(
        ForeignKey("vulnerability_candidates.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[str] = mapped_column(ForeignKey("authorized_targets.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    requested_by: Mapped[str | None] = mapped_column(String(128))
    request_options: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vulnerability: Mapped[VulnerabilityCandidate] = relationship(back_populates="validation_runs")
    target: Mapped[AuthorizedTarget] = relationship(back_populates="validation_runs")
    results: Mapped[list[ValidationResult]] = relationship(back_populates="run", cascade="all, delete-orphan")


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("authorized_targets.id", ondelete="RESTRICT"), index=True)
    method: Mapped[str] = mapped_column(String(8))
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    conclusion: Mapped[str] = mapped_column(String(64), index=True)
    request_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    response_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[ValidationRun] = relationship(back_populates="results")


class LLMAnalysis(Base):
    __tablename__ = "llm_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("payload_events.id", ondelete="CASCADE"), index=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(64), default="openai-compatible")
    model_name: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    request_hash: Mapped[str] = mapped_column(String(64), index=True)
    structured_result: Mapped[dict | None] = mapped_column(JSON)
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event: Mapped[PayloadEvent] = relationship(back_populates="llm_analyses")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    phase: Mapped[str] = mapped_column(String(64), default="queued", index=True)
    use_llm: Mapped[bool] = mapped_column(Boolean, default=True)
    llm_scope: Mapped[str] = mapped_column(String(16), default="suspicious")
    force: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    current_event_id: Mapped[str | None] = mapped_column(String(36), index=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    message: Mapped[str] = mapped_column(Text)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"), index=True)
    runtime: Mapped[str] = mapped_column(String(64))
    planner_used: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    plan: Mapped[list] = mapped_column(JSON, default=list)
    task_graph: Mapped[list] = mapped_column(JSON, default=list)
    answer: Mapped[str] = mapped_column(Text)
    warning: Mapped[str | None] = mapped_column(Text)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    tool_calls: Mapped[list[AgentToolCall]] = relationship(back_populates="session", cascade="all, delete-orphan")
    runs: Mapped[list[AgentRun]] = relationship(back_populates="session", cascade="all, delete-orphan")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("agent_sessions.id", ondelete="CASCADE"), index=True)
    collaboration_mode: Mapped[str] = mapped_column(String(64), index=True)
    runtime: Mapped[str] = mapped_column(String(64), index=True)
    planner_used: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    max_parallelism: Mapped[int] = mapped_column(Integer, default=1)
    llm_used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    consensus: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_gaps: Mapped[list] = mapped_column(JSON, default=list)
    task_graph: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[AgentSession] = relationship(back_populates="runs")
    messages: Mapped[list[AgentMessage]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("agent_sessions.id", ondelete="CASCADE"), index=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(64), index=True)
    task: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(32), default="result", index=True)
    recipient: Mapped[str | None] = mapped_column(String(64), index=True)
    follow_up_action: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    input_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    llm_used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="messages")


class AgentMemory(Base):
    __tablename__ = "agent_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"), index=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    memory_type: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (UniqueConstraint("session_id", "call_id", name="uq_agent_tool_call"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("agent_sessions.id", ondelete="CASCADE"), index=True)
    call_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(64), index=True)
    risk_level: Mapped[str] = mapped_column(String(32), index=True)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), index=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    session: Mapped[AgentSession] = relationship(back_populates="tool_calls")


class SavedHuntQuery(Base):
    __tablename__ = "saved_hunt_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), index=True)
    query: Mapped[str] = mapped_column(Text)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"), index=True)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str | None] = mapped_column(String(128), index=True)
    last_run_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    incident_type: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(Text)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    assignee: Mapped[str | None] = mapped_column(String(128), index=True)
    resolution: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    event_links: Mapped[list[IncidentEvent]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    reports: Mapped[list[IncidentReport]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    __table_args__ = (UniqueConstraint("incident_id", "event_id", name="uq_incident_event"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("payload_events.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(64), default="same_activity_cluster")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    incident: Mapped[Incident] = relationship(back_populates="event_links")
    event: Mapped[PayloadEvent] = relationship()


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("payload_events.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(32), index=True)
    attack_type: Mapped[str | None] = mapped_column(String(64), index=True)
    severity: Mapped[str | None] = mapped_column(String(16))
    review_status: Mapped[str] = mapped_column(String(32), default="confirmed")
    reviewer: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event: Mapped[PayloadEvent] = relationship(back_populates="annotations")


class IncidentReport(Base):
    __tablename__ = "incident_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    generator: Mapped[str] = mapped_column(String(32))
    model_name: Mapped[str | None] = mapped_column(String(128))
    content: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="reports")

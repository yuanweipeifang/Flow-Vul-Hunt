from __future__ import annotations

from ...models import AgentMessage, AgentRun, AgentToolCall
from ...schemas import AgentMessageOut, AgentRunOut, AgentToolCallOut
from .collaboration import CollaborationMessage


def tool_call_out(record: AgentToolCall) -> AgentToolCallOut:
    return AgentToolCallOut(
        id=record.call_id,
        name=record.name,
        risk_level=record.risk_level,
        arguments=record.arguments,
        status=record.status,
        requires_confirmation=record.requires_confirmation,
        result=record.result,
        error=record.error,
    )


def message_out(message: CollaborationMessage | AgentMessage) -> AgentMessageOut:
    return AgentMessageOut(
        id=message.id,
        agent_name=message.agent_name,
        role=message.role,
        task=message.task,
        input_summary=message.input_summary,
        output=message.output,
        depends_on=list(message.depends_on or []),
        evidence_refs=list(message.evidence_refs or []),
        confidence=float(message.confidence or 0.0),
        llm_used=bool(message.llm_used),
        status=message.status,
        error=message.error,
        created_at=getattr(message, "created_at", None),
    )


def run_out(run: AgentRun) -> AgentRunOut:
    return AgentRunOut(
        id=run.id,
        session_id=run.session_id,
        collaboration_mode=run.collaboration_mode,
        runtime=run.runtime,
        planner_used=run.planner_used,
        status=run.status,
        max_parallelism=run.max_parallelism,
        llm_used=run.llm_used,
        consensus=run.consensus,
        evidence_gaps=list(run.evidence_gaps or []),
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        messages=[message_out(message) for message in run.messages],
    )

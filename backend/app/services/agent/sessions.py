from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from ...config import Settings
from ...models import AgentMemory, AgentMessage, AgentRun, AgentSession, AgentToolCall, utcnow
from ...schemas import AgentChatRequest, AgentChatResult
from ...security import Actor
from .collaboration import CollaborationMessage


def store_agent_session(
    db: Session,
    session_id: str,
    actor: Actor,
    request: AgentChatRequest,
    result: AgentChatResult,
    settings: Settings,
    agents: list[CollaborationMessage] | None = None,
) -> None:
    task_graph = [task.model_dump(mode="json") for task in result.task_graph]
    session = AgentSession(
        id=session_id,
        actor=actor.name,
        role=actor.role,
        message=request.message,
        dataset_id=request.dataset_id,
        runtime=result.runtime,
        planner_used=result.planner_used,
        status="waiting_confirmation" if result.requires_confirmation else "completed",
        plan=result.plan,
        task_graph=task_graph,
        answer=result.answer,
        warning=result.warning,
        requires_confirmation=result.requires_confirmation,
    )
    db.add(session)
    for call in result.tool_calls:
        db.add(
            AgentToolCall(
                session_id=session_id,
                call_id=call.id,
                name=call.name,
                risk_level=call.risk_level,
                arguments=call.arguments,
                status=call.status,
                requires_confirmation=call.requires_confirmation,
                result=call.result if isinstance(call.result, dict) or call.result is None else {"value": call.result},
                error=call.error,
            )
        )
    if agents is not None:
        run = AgentRun(
            id=str(uuid4()),
            session_id=session_id,
            collaboration_mode=result.collaboration_mode,
            runtime=result.runtime,
            planner_used=result.planner_used,
            status="waiting_confirmation" if result.requires_confirmation else "completed",
            max_parallelism=settings.agent_max_parallelism,
            llm_used=result.llm_used,
            consensus=result.consensus,
            evidence_gaps=result.evidence_gaps,
            task_graph=task_graph,
            started_at=utcnow(),
            completed_at=utcnow(),
        )
        db.add(run)
        for message in agents:
            db.add(
                AgentMessage(
                    run_id=run.id,
                    session_id=session_id,
                    agent_name=message.agent_name,
                    role=message.role,
                    task=message.task,
                    message_type=message.message_type,
                    recipient=message.recipient,
                    follow_up_action=message.follow_up_action,
                    resolved=message.resolved,
                    input_summary=message.input_summary,
                    output=message.output,
                    depends_on=message.depends_on,
                    evidence_refs=message.evidence_refs,
                    confidence=message.confidence,
                    llm_used=message.llm_used,
                    status=message.status,
                    error=message.error,
                )
            )

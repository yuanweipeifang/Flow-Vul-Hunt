from __future__ import annotations

from ...models import AgentMemory, AgentMessage, AgentRun, AgentToolCall
from ...schemas import AgentMemoryOut, AgentMessageOut, AgentRunOut, AgentTaskSpecOut, AgentToolCallOut
from .collaboration import CollaborationMessage
from .constants import AgentTaskSpec


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


def task_spec_out(task: AgentTaskSpec) -> AgentTaskSpecOut:
    return AgentTaskSpecOut(
        task_id=task.task_id,
        agent_name=task.agent_name,
        goal=task.goal,
        tool_names=list(task.tool_names or []),
        depends_on=list(task.depends_on or []),
        priority=task.priority,
        requires_confirmation=task.requires_confirmation,
    )


def task_graph_out(items: list[dict] | list[AgentTaskSpec]) -> list[AgentTaskSpecOut]:
    output: list[AgentTaskSpecOut] = []
    for item in items:
        if isinstance(item, AgentTaskSpec):
            output.append(task_spec_out(item))
        else:
            output.append(AgentTaskSpecOut.model_validate(item))
    return output


def message_out(message: CollaborationMessage | AgentMessage) -> AgentMessageOut:
    return AgentMessageOut(
        id=message.id,
        agent_name=message.agent_name,
        role=message.role,
        task=message.task,
        message_type=getattr(message, "message_type", "result"),
        recipient=getattr(message, "recipient", None),
        follow_up_action=dict(getattr(message, "follow_up_action", {}) or {}),
        resolved=bool(getattr(message, "resolved", True)),
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
        task_graph=task_graph_out(list(run.task_graph or [])),
        messages=[message_out(message) for message in run.messages],
    )


def memory_out(memory: AgentMemory) -> AgentMemoryOut:
    return AgentMemoryOut(
        id=memory.id,
        dataset_id=memory.dataset_id,
        agent_name=memory.agent_name,
        memory_type=memory.memory_type,
        summary=memory.summary,
        content=memory.content,
        confidence=memory.confidence,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )

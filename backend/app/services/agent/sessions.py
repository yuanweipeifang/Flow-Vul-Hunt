from __future__ import annotations

import json
import urllib.request
from uuid import uuid4

from sqlalchemy.orm import Session

from ...config import Settings
from ...models import AgentMemory, AgentMessage, AgentRun, AgentSession, AgentToolCall, utcnow
from ...schemas import AgentChatRequest, AgentChatResult
from ...security import Actor
from .collaboration import CollaborationMessage


# #region debug-point shared:agent-chat-stall
def _debug_event(hypothesis_id: str, location: str, msg: str, data: dict | None = None) -> None:
    payload = {
        "sessionId": "agent-chat-stall",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": location,
        "msg": f"[DEBUG] {msg}",
        "data": data or {},
    }
    url = "http://127.0.0.1:7777/event"
    env_path = ".dbg/agent-chat-stall.env"
    try:
        with open(env_path, encoding="utf-8") as env_file:
            for line in env_file:
                if line.startswith("DEBUG_SERVER_URL="):
                    url = line.split("=", 1)[1].strip() or url
    except Exception:
        pass
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=1,
        ).read()
    except Exception:
        pass


# #endregion


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
    # #region debug-point B:store-session-start
    _debug_event(
        "B",
        "backend/app/services/agent/sessions.py:store_agent_session:start",
        "storing agent session",
        {
            "session_id": session_id,
            "result_task_graph_count": len(result.task_graph),
            "serialized_task_graph_count": len(task_graph),
            "tool_call_count": len(result.tool_calls),
            "agent_message_count": len(agents or []),
        },
    )
    # #endregion
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
    # #region debug-point B:session-row-added
    _debug_event(
        "B",
        "backend/app/services/agent/sessions.py:store_agent_session:session_row",
        "agent session row added",
        {
            "session_id": session_id,
            "session_task_graph_count": len(session.task_graph or []),
            "session_status": session.status,
        },
    )
    # #endregion
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
        # #region debug-point B:run-row-added
        _debug_event(
            "B",
            "backend/app/services/agent/sessions.py:store_agent_session:run_row",
            "agent run row added",
            {
                "session_id": session_id,
                "run_id": run.id,
                "run_task_graph_count": len(run.task_graph or []),
                "run_status": run.status,
                "message_count": len(agents),
            },
        )
        # #endregion
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
        # #region debug-point B:messages-added
        _debug_event(
            "B",
            "backend/app/services/agent/sessions.py:store_agent_session:messages",
            "agent messages queued for insert",
            {
                "session_id": session_id,
                "run_id": run.id,
                "message_ids": [message.id for message in agents],
                "message_types": [message.message_type for message in agents],
            },
        )
        # #endregion

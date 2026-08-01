from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...audit import audit_log
from ...config import Settings, get_settings
from ...llm.gateway import LLMResponseError, LLMUnavailableError
from ...models import AgentRun, AgentSession
from ...schemas import AgentChatRequest, AgentChatResult, AgentToolCallOut
from ...security import Actor
from .collaboration import CollaborationMessage, build_collaboration
from .isolation import agent_status
from .mappers import message_out, task_graph_out, tool_call_out
from .orchestrator import AgentOrchestrator
from .planner import hermes_planned_tools, planned_task_graph_fallback
from .sessions import store_agent_session
from .tools import execute_tool


# #region debug-point shared:agent-chat-stall
def _debug_event(hypothesis_id: str, location: str, msg: str, data: dict[str, Any] | None = None) -> None:
    _payload = {
        "sessionId": "agent-chat-stall",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": location,
        "msg": f"[DEBUG] {msg}",
        "data": data or {},
    }
    _url = "http://127.0.0.1:7777/event"
    _env_path = ".dbg/agent-chat-stall.env"
    try:
        with open(_env_path, encoding="utf-8") as _env_file:
            for _line in _env_file:
                if _line.startswith("DEBUG_SERVER_URL="):
                    _url = _line.split("=", 1)[1].strip() or _url
    except Exception:
        pass
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                _url,
                data=json.dumps(_payload).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=1,
        ).read()
    except Exception:
        pass


# #endregion


def run_agent_chat(
    request: AgentChatRequest,
    db: Session,
    background_tasks: BackgroundTasks,
    actor: Actor,
    settings: Settings | None = None,
    event_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> AgentChatResult:
    settings = settings or get_settings()
    status = agent_status(settings)
    _emit_agent_event(
        event_callback,
        "started",
        {
            "runtime": status.runtime,
            "hermes_isolated": status.hermes_isolated,
            "collaboration_enabled": settings.agent_collaboration_enabled,
        },
    )
    # #region debug-point A:chat-entry
    _debug_event(
        "A",
        "backend/app/services/agent/chat.py:run_agent_chat:entry",
        "entered run_agent_chat",
        {
            "message_len": len(request.message),
            "dataset_id": request.dataset_id,
            "auto_execute": request.auto_execute,
            "confirmed_tool_call_ids": request.confirmed_tool_call_ids,
        },
    )
    # #endregion
    if not status.hermes_isolated:
        raise HTTPException(status_code=500, detail="Hermes config/plugin directories must stay inside this project")

    allowed = set(settings.agent_allowed_tools)
    session_id = str(uuid4())
    warning = None
    planner_used = "local"
    final_focus = None
    _emit_agent_event(
        event_callback,
        "planner_started",
        {"hermes_available": status.hermes_available, "llm_enabled": settings.llm_enabled},
    )
    if status.hermes_available and settings.llm_enabled:
        try:
            plan, planned, tasks, final_focus = hermes_planned_tools(request, settings, allowed)
            planner_used = "hermes"
        except (LLMUnavailableError, LLMResponseError, RuntimeError) as exc:
            plan, planned, tasks, final_focus = planned_task_graph_fallback(request)
            warning = f"Hermes planner unavailable; local planner used: {exc}"
    else:
        plan, planned, tasks, final_focus = planned_task_graph_fallback(request)
        if not status.hermes_available:
            warning = "Hermes 包尚未安装，当前使用本项目内置 planner；接口和隔离目录已就绪。"
    _emit_agent_event(
        event_callback,
        "planner_finished",
        {
            "planner_used": planner_used,
            "plan": plan,
            "planned_tool_count": len(planned),
            "task_graph": [task.model_dump(mode="json") for task in tasks],
            "warning": warning,
            "final_focus": final_focus,
        },
    )
    # #region debug-point A:planner-output
    _debug_event(
        "A",
        "backend/app/services/agent/chat.py:run_agent_chat:planner",
        "planner finished",
        {
            "planner_used": planner_used,
            "plan_count": len(plan),
            "planned_tool_count": len(planned),
            "task_count": len(tasks),
            "task_ids": [task.task_id for task in tasks],
            "task_agents": [task.agent_name for task in tasks],
            "warning": warning,
            "final_focus": final_focus,
        },
    )
    # #endregion

    orchestrator = AgentOrchestrator(settings)
    _emit_agent_event(
        event_callback,
        "orchestrator_started",
        {"task_count": len(tasks), "planned_tool_count": len(planned)},
    )
    # #region debug-point C:orchestrator-start
    _debug_event(
        "C",
        "backend/app/services/agent/chat.py:run_agent_chat:orchestrator_start",
        "starting orchestrator execution",
        {"task_count": len(tasks), "planned_tool_count": len(planned)},
    )
    # #endregion
    tool_calls, role_executions, consensus, evidence_gaps, collaboration_answer = orchestrator.execute(
        request=request,
        tasks=tasks,
        planned=planned,
        db=db,
        background_tasks=background_tasks,
        allowed=allowed,
        event_callback=event_callback,
    )
    _emit_agent_event(
        event_callback,
        "orchestrator_finished",
        {
            "tool_call_count": len(tool_calls),
            "role_execution_count": len(role_executions),
            "evidence_gap_count": len(evidence_gaps),
        },
    )
    # #region debug-point C:orchestrator-finish
    _debug_event(
        "C",
        "backend/app/services/agent/chat.py:run_agent_chat:orchestrator_finish",
        "orchestrator execution finished",
        {
            "tool_call_count": len(tool_calls),
            "executed_tool_count": len([call for call in tool_calls if call.status == "executed"]),
            "blocked_tool_count": len([call for call in tool_calls if call.status == "blocked"]),
            "failed_tool_count": len([call for call in tool_calls if call.status == "failed"]),
            "role_execution_count": len(role_executions),
            "role_statuses": {execution.task.task_id: execution.status for execution in role_executions},
            "evidence_gap_count": len(evidence_gaps),
        },
    )
    # #endregion
    requires_confirmation = any(call.status == "blocked" and call.requires_confirmation for call in tool_calls)
    collaboration_mode = "multi_agent" if settings.agent_collaboration_enabled else "single_planner"
    agents: list[CollaborationMessage] = []
    answer = collaboration_answer
    if settings.agent_collaboration_enabled:
        _emit_agent_event(event_callback, "collaboration_started", {"role_execution_count": len(role_executions)})
        agents, consensus, evidence_gaps, collaboration_answer = build_collaboration(
            request, planned, tool_calls, settings, role_executions
        )
        answer = f"{collaboration_answer} 工具执行概况：计划 {len(planned)} 步，已执行 {len([call for call in tool_calls if call.status == 'executed'])} 个。"
        if requires_confirmation:
            answer += " 高风险工具仍需确认。"
        _emit_agent_event(event_callback, "collaboration_finished", {"agent_message_count": len(agents)})
    llm_used = planner_used == "hermes" or any(execution.llm_used for execution in role_executions)
    result = AgentChatResult(
        session_id=session_id,
        runtime=status.runtime,
        hermes_isolated=status.hermes_isolated,
        plan=plan,
        tool_calls=tool_calls,
        answer=answer,
        requires_confirmation=requires_confirmation,
        warning=warning,
        planner_used=planner_used,
        collaboration_mode=collaboration_mode,
        task_graph=task_graph_out(tasks),
        agents=[message_out(message) for message in agents],
        consensus=consensus,
        evidence_gaps=evidence_gaps,
        llm_used=llm_used,
    )
    # #region debug-point B:result-built
    _debug_event(
        "B",
        "backend/app/services/agent/chat.py:run_agent_chat:result",
        "agent chat result built",
        {
            "session_id": session_id,
            "result_task_graph_count": len(result.task_graph),
            "agent_message_count": len(result.agents),
            "requires_confirmation": result.requires_confirmation,
            "collaboration_mode": result.collaboration_mode,
            "llm_used": result.llm_used,
        },
    )
    # #endregion
    store_agent_session(db, session_id, actor, request, result, settings, agents if settings.agent_collaboration_enabled else None)
    audit_log(
        db,
        "agent.chat",
        "agent_session",
        session_id,
        {
            "actor": actor.name,
            "runtime": status.runtime,
            "planner_used": planner_used,
            "collaboration_mode": collaboration_mode,
            "agents": [message.agent_name for message in agents],
            "tool_calls": [{"name": call.name, "status": call.status} for call in tool_calls],
        },
    )
    db.commit()
    _emit_agent_event(
        event_callback,
        "result",
        {
            "session_id": session_id,
            "requires_confirmation": result.requires_confirmation,
            "llm_used": result.llm_used,
            "result": result.model_dump(mode="json"),
        },
    )
    # #region debug-point B:commit-finished
    _debug_event(
        "B",
        "backend/app/services/agent/chat.py:run_agent_chat:commit",
        "agent session committed",
        {
            "session_id": session_id,
            "db_session_new": len(db.new),
            "db_session_dirty": len(db.dirty),
        },
    )
    # #endregion
    return result


def _emit_agent_event(
    event_callback: Callable[[str, dict[str, Any]], None] | None,
    event: str,
    data: dict[str, Any],
) -> None:
    if event_callback:
        event_callback(event, data)


def confirm_agent_tools(
    session_id: str,
    tool_call_ids: list[str],
    db: Session,
    background_tasks: BackgroundTasks,
    actor: Actor,
    settings: Settings | None = None,
) -> AgentChatResult:
    settings = settings or get_settings()
    session = db.scalar(
        select(AgentSession)
        .where(AgentSession.id == session_id)
        .options(selectinload(AgentSession.tool_calls), selectinload(AgentSession.runs).selectinload(AgentRun.messages))
    )
    if not session:
        raise HTTPException(status_code=404, detail="agent session not found")
    wanted = set(tool_call_ids)
    for record in session.tool_calls:
        if record.call_id not in wanted:
            continue
        if record.status != "blocked" or not record.requires_confirmation:
            continue
        if record.name not in set(settings.agent_allowed_tools):
            record.status = "blocked"
            record.error = "tool is not allowed by AGENT_ALLOWED_TOOLS"
            continue
        try:
            record.result = execute_tool(db, background_tasks, record.name, record.arguments)
            record.status = "executed"
            record.error = None
        except HTTPException as exc:
            record.status = "failed"
            record.error = str(exc.detail)
        except Exception as exc:
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"[:500]
    session.requires_confirmation = any(
        call.status == "blocked" and call.requires_confirmation for call in session.tool_calls
    )
    session.status = "waiting_confirmation" if session.requires_confirmation else "completed"
    session.answer = "已执行确认后的工具调用。" if not session.requires_confirmation else "部分工具仍在等待确认。"
    for run in session.runs:
        run.status = session.status
        if run.consensus:
            run.consensus = {**run.consensus, "confirmation_status": session.status}
    audit_log(
        db,
        "agent.tool.confirm",
        "agent_session",
        session_id,
        {"actor": actor.name, "tool_call_ids": tool_call_ids},
    )
    db.commit()
    db.refresh(session)
    return AgentChatResult(
        session_id=session.id,
        runtime=session.runtime,
        hermes_isolated=agent_status(settings).hermes_isolated,
        plan=session.plan,
        tool_calls=[tool_call_out(call) for call in session.tool_calls],
        answer=session.answer,
        requires_confirmation=session.requires_confirmation,
        warning=session.warning,
        planner_used=session.planner_used,
        collaboration_mode=session.runs[-1].collaboration_mode if session.runs else "single_planner",
        agents=[message_out(message) for run in session.runs for message in run.messages],
        consensus=session.runs[-1].consensus if session.runs else {},
        evidence_gaps=list(session.runs[-1].evidence_gaps or []) if session.runs else [],
        llm_used=bool(session.runs[-1].llm_used) if session.runs else session.planner_used == "hermes",
    )

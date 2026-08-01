from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...audit import audit_log
from ...config import Settings, get_settings
from ...llm.gateway import LLMGateway, LLMResponseError, LLMUnavailableError
from ...models import AgentRun, AgentSession
from ...schemas import AgentAnswerDraft, AgentChatRequest, AgentChatResult, AgentToolCallOut
from ...security import Actor
from .collaboration import CollaborationMessage, build_collaboration
from .isolation import agent_status
from .mappers import message_out, task_graph_out, tool_call_out
from .orchestrator import AgentOrchestrator
from .planner import hermes_planned_tools, planned_task_graph_fallback
from .sessions import store_agent_session
from .tools import execute_tool

_CHAT_SYSTEM_PROMPT = """You are Flow-Vul-Hunt's security analysis agent.
Return one JSON object only. Answer in Chinese.

Use the supplied dataset metadata, stored CSV samples, hunt results, attack-surface summaries, vulnerability candidates, and tool evidence.
If CSV samples are present, explicitly use them as traffic evidence.
Do not invent assets, exploit success, attacker identity, CVEs, or validation results.
Keep active validation recommendations inside the project's safe workflow.

Schema:
{
  "answer": "direct answer for the user",
  "key_observations": ["evidence-backed observation"],
  "suggested_next_questions": ["short follow-up question the user can ask"]
}
"""


def _looks_like_replacement_mojibake(text: str) -> bool:
    compact = "".join(char for char in text.strip() if not char.isspace())
    if len(compact) < 6 or "?" not in compact:
        return False
    question_ratio = compact.count("?") / len(compact)
    if question_ratio >= 0.8:
        return True
    return question_ratio >= 0.6 and any(char.isalnum() for char in compact)


def _compact_tool_calls(tool_calls: list[AgentToolCallOut]) -> list[dict[str, Any]]:
    compact = []
    for call in tool_calls:
        result = call.result
        if isinstance(result, (dict, list)):
            serialized = json.dumps(result, ensure_ascii=False, default=str)
            if len(serialized) > 12000:
                serialized = serialized[:12000] + "\n[TRUNCATED]"
            result = serialized
        compact.append(
            {
                "name": call.name,
                "status": call.status,
                "arguments": call.arguments,
                "error": call.error,
                "result": result,
            }
        )
    return compact


def _llm_chat_answer(
    request: AgentChatRequest,
    tool_calls: list[AgentToolCallOut],
    consensus: dict[str, Any],
    settings: Settings,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    if not settings.llm_enabled:
        return None, None, "LLM provider is not configured"
    payload = {
        "user_message": request.message,
        "dataset_id": request.dataset_id,
        "tool_calls": _compact_tool_calls(tool_calls),
        "consensus": consensus,
    }
    try:
        result = LLMGateway(settings).complete_json(
            _CHAT_SYSTEM_PROMPT,
            payload,
            AgentAnswerDraft,
            agent_name="security_brain",
        )
    except Exception as exc:
        return None, None, f"LLM answer unavailable: {exc}"
    draft = result.data
    answer = draft.answer.strip()
    if draft.key_observations:
        answer += "\n\n关键观察：\n" + "\n".join(f"- {item}" for item in draft.key_observations)
    if draft.suggested_next_questions:
        answer += "\n\n你可以继续问：\n" + "\n".join(f"- {item}" for item in draft.suggested_next_questions)
    return answer, {
        "provider": result.provider_name,
        "model": result.model_name,
        "latency_ms": result.latency_ms,
        "token_usage": result.token_usage,
    }, None


def run_agent_chat(
    request: AgentChatRequest,
    db: Session,
    background_tasks: BackgroundTasks,
    actor: Actor,
    settings: Settings | None = None,
    event_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> AgentChatResult:
    if _looks_like_replacement_mojibake(request.message):
        raise HTTPException(
            status_code=422,
            detail=(
                "message appears to be corrupted by terminal encoding; use UTF-8 input "
                "or send the request from the browser/API client"
            ),
        )
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
    orchestrator = AgentOrchestrator(settings)
    _emit_agent_event(
        event_callback,
        "orchestrator_started",
        {"task_count": len(tasks), "planned_tool_count": len(planned)},
    )
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
    requires_confirmation = any(call.status == "blocked" and call.requires_confirmation for call in tool_calls)
    collaboration_mode = "multi_agent" if settings.agent_collaboration_enabled else "single_planner"
    agents: list[CollaborationMessage] = []
    answer = collaboration_answer
    if settings.agent_collaboration_enabled:
        _emit_agent_event(event_callback, "collaboration_started", {"role_execution_count": len(role_executions)})
        agents, consensus, evidence_gaps, collaboration_answer = build_collaboration(
            request, planned, tool_calls, settings, role_executions
        )
    executed_count = sum(call.status == "executed" for call in tool_calls)
    blocked_count = sum(call.status == "blocked" for call in tool_calls)
    if settings.agent_collaboration_enabled:
        answer = (
            f"{collaboration_answer} 工具执行概况："
            f"计划 {len(planned)} 步，已执行 {executed_count} 个。"
        )
        if requires_confirmation or blocked_count:
            answer += " 仍有受策略限制或需确认的工具。"
        _emit_agent_event(event_callback, "collaboration_finished", {"agent_message_count": len(agents)})

    llm_used = planner_used == "hermes" or any(
        execution.llm_used for execution in role_executions
    )
    llm_answer, llm_meta, llm_warning = _llm_chat_answer(
        request,
        tool_calls,
        consensus,
        settings,
    )
    if llm_answer:
        answer = llm_answer
        llm_used = True
        consensus = {**consensus, "llm_answer": llm_meta}
    elif llm_warning:
        warning = f"{warning}; {llm_warning}" if warning else llm_warning
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
        task_graph=task_graph_out(list(session.task_graph or [])),
        agents=[message_out(message) for run in session.runs for message in run.messages],
        consensus=session.runs[-1].consensus if session.runs else {},
        evidence_gaps=list(session.runs[-1].evidence_gaps or []) if session.runs else [],
        llm_used=bool(session.runs[-1].llm_used) if session.runs else session.planner_used == "hermes",
    )

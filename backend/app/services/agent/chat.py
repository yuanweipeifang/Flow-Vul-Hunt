from __future__ import annotations

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
from .mappers import message_out, tool_call_out
from .planner import hermes_planned_tools, planned_tools_fallback
from .sessions import store_agent_session
from .tools import _risk_level, execute_tool

_LOCAL_PLAN = [
    "确认数据集范围和当前状态",
    "执行威胁狩猎并默认排除已确认误报",
    "汇总漏洞候选并给出研判重点",
    "高风险动作在确认后再执行",
]


def run_agent_chat(
    request: AgentChatRequest,
    db: Session,
    background_tasks: BackgroundTasks,
    actor: Actor,
    settings: Settings | None = None,
) -> AgentChatResult:
    settings = settings or get_settings()
    status = agent_status(settings)
    if not status.hermes_isolated:
        raise HTTPException(status_code=500, detail="Hermes config/plugin directories must stay inside this project")

    allowed = set(settings.agent_allowed_tools)
    session_id = str(uuid4())
    max_steps = request.max_steps or settings.agent_max_steps
    warning = None
    planner_used = "local"
    final_focus = None
    if status.hermes_available and settings.llm_enabled:
        try:
            plan, planned, final_focus = hermes_planned_tools(request, settings, allowed)
            planned = planned[:max_steps]
            planner_used = "hermes"
        except (LLMUnavailableError, LLMResponseError, RuntimeError) as exc:
            planned = planned_tools_fallback(request)[:max_steps]
            plan = _LOCAL_PLAN
            warning = f"Hermes planner unavailable; local planner used: {exc}"
    else:
        planned = planned_tools_fallback(request)[:max_steps]
        plan = _LOCAL_PLAN
        if not status.hermes_available:
            warning = "Hermes 包尚未安装，当前使用本项目内置 planner；接口和隔离目录已就绪。"
    tool_calls: list[AgentToolCallOut] = []
    requires_confirmation = False

    for index, planned_call in enumerate(planned, start=1):
        name = planned_call["name"]
        call_id = f"tool-{index}"
        risk_level = _risk_level(name)
        call = AgentToolCallOut(
            id=call_id,
            name=name,
            risk_level=risk_level,
            arguments=planned_call["arguments"],
            status="planned",
            requires_confirmation=risk_level == "high_risk",
        )
        if name not in allowed:
            call.status = "blocked"
            call.error = "tool is not allowed by AGENT_ALLOWED_TOOLS"
        elif call.requires_confirmation and (
            settings.agent_require_confirmation
            and (not request.auto_execute or call_id not in request.confirmed_tool_call_ids)
        ):
            call.status = "blocked"
            call.error = "confirmation required before executing this high-risk tool"
            requires_confirmation = True
        elif request.auto_execute or risk_level == "read_only":
            try:
                call.result = execute_tool(db, background_tasks, name, planned_call["arguments"])
                call.status = "executed"
            except HTTPException as exc:
                call.status = "failed"
                call.error = str(exc.detail)
            except Exception as exc:
                call.status = "failed"
                call.error = f"{type(exc).__name__}: {exc}"[:500]
        tool_calls.append(call)

    executed = [call for call in tool_calls if call.status == "executed"]
    blocked = [call for call in tool_calls if call.status == "blocked"]
    answer = f"已生成 {len(planned)} 步安全分析计划，执行 {len(executed)} 个工具。"
    if blocked:
        answer += f" 有 {len(blocked)} 个工具被策略拦截或等待确认。"
    if final_focus:
        answer += f" 重点：{final_focus}"
    agents: list[CollaborationMessage] = []
    consensus: dict[str, Any] = {}
    evidence_gaps: list[str] = []
    collaboration_mode = "single_planner"
    llm_used = planner_used == "hermes"
    if settings.agent_collaboration_enabled:
        collaboration_mode = "multi_agent"
        agents, consensus, evidence_gaps, collaboration_answer = build_collaboration(
            request, planned, tool_calls, settings
        )
        answer = f"{collaboration_answer} 工具执行概况：计划 {len(planned)} 步，已执行 {len(executed)} 个。"
        if blocked:
            answer += f" {len(blocked)} 个高风险或受限工具仍需确认。"
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
    return result


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

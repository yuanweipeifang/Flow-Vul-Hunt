from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import AgentMemory, AgentRun, AgentSession
from ..schemas import AgentChatRequest, AgentChatResult, AgentConfirmRequest, AgentMemoryOut, AgentSessionOut, AgentStatusOut, AgentTraceOut
from ..security import Actor, get_actor, require_roles
from ..services.agent import agent_status, confirm_agent_tools, hermes_smoke_check, memory_out, run_agent_chat, run_out, task_graph_out, tool_call_out


router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status", response_model=AgentStatusOut)
def get_agent_status(_actor: Actor = Depends(get_actor)) -> AgentStatusOut:
    return agent_status()


@router.get("/hermes/smoke")
def get_hermes_smoke(_actor: Actor = Depends(get_actor)) -> dict:
    return hermes_smoke_check()


@router.get("/memory", response_model=list[AgentMemoryOut])
def list_agent_memory(
    dataset_id: str | None = None,
    agent_name: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> list[AgentMemoryOut]:
    statement = select(AgentMemory)
    if dataset_id:
        statement = statement.where(AgentMemory.dataset_id == dataset_id)
    if agent_name:
        statement = statement.where(AgentMemory.agent_name == agent_name)
    rows = db.scalars(statement.order_by(AgentMemory.created_at.desc()).limit(min(max(limit, 1), 200))).all()
    return [memory_out(row) for row in rows]


@router.post("/chat", response_model=AgentChatResult)
def agent_chat(
    request: AgentChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles("admin", "analyst")),
) -> AgentChatResult:
    settings = get_settings()
    if not settings.agent_enabled:
        raise HTTPException(status_code=503, detail="agent is disabled; set AGENT_ENABLED=true")
    return run_agent_chat(request, db, background_tasks, actor, settings)


@router.get("/sessions", response_model=list[AgentSessionOut])
def list_agent_sessions(
    dataset_id: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> list[AgentSessionOut]:
    statement = select(AgentSession).options(
        selectinload(AgentSession.tool_calls), selectinload(AgentSession.runs).selectinload(AgentRun.messages)
    )
    if dataset_id:
        statement = statement.where(AgentSession.dataset_id == dataset_id)
    rows = db.scalars(statement.order_by(AgentSession.created_at.desc()).limit(min(max(limit, 1), 200))).all()
    return [_session_out(row) for row in rows]


@router.get("/sessions/{session_id}", response_model=AgentSessionOut)
def get_agent_session(
    session_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> AgentSessionOut:
    session = db.scalar(
        select(AgentSession)
        .where(AgentSession.id == session_id)
        .options(selectinload(AgentSession.tool_calls), selectinload(AgentSession.runs).selectinload(AgentRun.messages))
    )
    if not session:
        raise HTTPException(status_code=404, detail="agent session not found")
    return _session_out(session)


@router.get("/sessions/{session_id}/trace", response_model=AgentTraceOut)
def get_agent_session_trace(
    session_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> AgentTraceOut:
    session = db.scalar(
        select(AgentSession)
        .where(AgentSession.id == session_id)
        .options(selectinload(AgentSession.tool_calls), selectinload(AgentSession.runs).selectinload(AgentRun.messages))
    )
    if not session:
        raise HTTPException(status_code=404, detail="agent session not found")
    return AgentTraceOut(session=_session_out(session), runs=[run_out(run) for run in session.runs])


@router.post("/sessions/{session_id}/confirm", response_model=AgentChatResult)
def confirm_agent_session_tools(
    session_id: str,
    request: AgentConfirmRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles("admin", "analyst")),
) -> AgentChatResult:
    return confirm_agent_tools(session_id, request.tool_call_ids, db, background_tasks, actor)


def _session_out(session: AgentSession) -> AgentSessionOut:
    return AgentSessionOut(
        id=session.id,
        actor=session.actor,
        role=session.role,
        message=session.message,
        dataset_id=session.dataset_id,
        runtime=session.runtime,
        planner_used=session.planner_used,
        status=session.status,
        plan=session.plan,
        answer=session.answer,
        warning=session.warning,
        requires_confirmation=session.requires_confirmation,
        created_at=session.created_at,
        updated_at=session.updated_at,
        task_graph=task_graph_out(list(session.task_graph or [])),
        tool_calls=[tool_call_out(call) for call in session.tool_calls],
        runs=[run_out(run) for run in session.runs],
    )

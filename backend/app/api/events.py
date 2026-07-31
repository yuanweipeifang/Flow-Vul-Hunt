from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..audit import audit_log
from ..models import DetectionFinding, ExtractedFeature, PayloadEvent
from ..schemas import (
    AnalyzeRequest,
    EventDetail,
    ExtractedFeatureOut,
    PaginatedEvents,
)
from ..services.analysis_service import analyze_event
from ..services.event_mapper import event_detail, event_summary
from ..services.vulnerability_service import compute_event_features
from ..security import Actor, get_actor, require_roles


router = APIRouter(prefix="/events", tags=["events"])


def _filtered_events_statement(
    dataset_id: str | None = None,
    verdict: str | None = None,
    attack_type: str | None = None,
    min_risk: float | None = None,
    host: str | None = None,
    is_binary: bool | None = None,
):
    statement = select(PayloadEvent)
    if attack_type:
        statement = statement.join(DetectionFinding)
        statement = statement.where(DetectionFinding.attack_type == attack_type)
    for condition in (
        PayloadEvent.dataset_id == dataset_id if dataset_id else None,
        PayloadEvent.verdict == verdict if verdict else None,
        PayloadEvent.risk_score >= min_risk if min_risk is not None else None,
        PayloadEvent.host.ilike(f"%{host}%") if host else None,
        PayloadEvent.is_binary == is_binary if is_binary is not None else None,
    ):
        if condition is not None:
            statement = statement.where(condition)
    return statement.distinct()


@router.get("", response_model=PaginatedEvents)
def list_events(
    dataset_id: str | None = None,
    verdict: str | None = None,
    attack_type: str | None = None,
    min_risk: float | None = Query(default=None, ge=0, le=100),
    host: str | None = None,
    is_binary: bool | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> PaginatedEvents:
    statement = _filtered_events_statement(dataset_id, verdict, attack_type, min_risk, host, is_binary)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = list(
        db.scalars(
            statement.distinct()
            .order_by(PayloadEvent.risk_score.desc(), PayloadEvent.row_number)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return PaginatedEvents(total=total, offset=offset, limit=limit, items=[event_summary(event) for event in items])


@router.get("/{event_id}", response_model=EventDetail)
def get_event(event_id: str, db: Session = Depends(get_db), _actor: Actor = Depends(get_actor)) -> PayloadEvent:
    event = db.scalar(
        select(PayloadEvent)
        .where(PayloadEvent.id == event_id)
        .options(
            selectinload(PayloadEvent.findings),
            selectinload(PayloadEvent.llm_analyses),
        )
    )
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    return event_detail(event)


@router.get("/{event_id}/features", response_model=ExtractedFeatureOut)
def get_event_features(event_id: str, db: Session = Depends(get_db), _actor: Actor = Depends(get_actor)) -> dict:
    event = db.get(PayloadEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    feature = db.scalar(select(ExtractedFeature).where(ExtractedFeature.event_id == event_id))
    if feature:
        return {
            "id": feature.id,
            "event_id": feature.event_id,
            "feature_version": feature.feature_version,
            "features": feature.features,
            "created_at": feature.created_at,
            "updated_at": feature.updated_at,
        }
    return {
        "id": None,
        "event_id": event.id,
        "feature_version": "1.0",
        "features": compute_event_features(event),
        "created_at": None,
        "updated_at": None,
    }


@router.post("/{event_id}/reanalyze", response_model=EventDetail)
def reanalyze_event(
    event_id: str,
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> PayloadEvent:
    event = db.scalar(
        select(PayloadEvent)
        .where(PayloadEvent.id == event_id)
        .options(
            selectinload(PayloadEvent.findings),
            selectinload(PayloadEvent.llm_analyses),
        )
    )
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    analyze_event(db, event, request.use_llm, request.llm_scope, force=True)
    audit_log(db, "event.reanalyze", "event", event_id, {"use_llm": request.use_llm})
    db.commit()
    db.expire(event)
    refreshed = db.scalar(
        select(PayloadEvent)
        .where(PayloadEvent.id == event_id)
        .options(
            selectinload(PayloadEvent.findings),
            selectinload(PayloadEvent.llm_analyses),
        )
    )
    return event_detail(refreshed)

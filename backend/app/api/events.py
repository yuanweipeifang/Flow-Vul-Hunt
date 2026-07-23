from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Annotation, DetectionFinding, ExtractedFeature, PayloadEvent
from ..schemas import (
    AnalyzeRequest,
    AnnotationCreate,
    AnnotationOut,
    EventDetail,
    ExtractedFeatureOut,
    PaginatedEvents,
)
from ..services.analysis_service import analyze_event
from ..services.vulnerability_service import compute_event_features


router = APIRouter(prefix="/events", tags=["events"])


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
) -> PaginatedEvents:
    statement = select(PayloadEvent)
    count_statement = select(func.count(func.distinct(PayloadEvent.id))).select_from(PayloadEvent)
    if attack_type:
        statement = statement.join(DetectionFinding)
        count_statement = count_statement.join(DetectionFinding)
        statement = statement.where(DetectionFinding.attack_type == attack_type)
        count_statement = count_statement.where(DetectionFinding.attack_type == attack_type)
    for condition in (
        PayloadEvent.dataset_id == dataset_id if dataset_id else None,
        PayloadEvent.verdict == verdict if verdict else None,
        PayloadEvent.risk_score >= min_risk if min_risk is not None else None,
        PayloadEvent.host.ilike(f"%{host}%") if host else None,
        PayloadEvent.is_binary == is_binary if is_binary is not None else None,
    ):
        if condition is not None:
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
    total = db.scalar(count_statement) or 0
    items = list(
        db.scalars(
            statement.distinct().order_by(PayloadEvent.risk_score.desc(), PayloadEvent.row_number).offset(offset).limit(limit)
        ).all()
    )
    return PaginatedEvents(total=total, offset=offset, limit=limit, items=items)


@router.get("/{event_id}", response_model=EventDetail)
def get_event(event_id: str, db: Session = Depends(get_db)) -> PayloadEvent:
    event = db.scalar(
        select(PayloadEvent)
        .where(PayloadEvent.id == event_id)
        .options(
            selectinload(PayloadEvent.findings),
            selectinload(PayloadEvent.llm_analyses),
            selectinload(PayloadEvent.annotations),
        )
    )
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    return event


@router.get("/{event_id}/features", response_model=ExtractedFeatureOut)
def get_event_features(event_id: str, db: Session = Depends(get_db)) -> dict:
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
    event_id: str, request: AnalyzeRequest, db: Session = Depends(get_db)
) -> PayloadEvent:
    event = db.scalar(
        select(PayloadEvent)
        .where(PayloadEvent.id == event_id)
        .options(
            selectinload(PayloadEvent.findings),
            selectinload(PayloadEvent.llm_analyses),
            selectinload(PayloadEvent.annotations),
        )
    )
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    analyze_event(db, event, request.use_llm, request.llm_scope, force=True)
    db.commit()
    db.expire(event)
    return db.scalar(
        select(PayloadEvent)
        .where(PayloadEvent.id == event_id)
        .options(
            selectinload(PayloadEvent.findings),
            selectinload(PayloadEvent.llm_analyses),
            selectinload(PayloadEvent.annotations),
        )
    )


@router.post("/{event_id}/annotations", response_model=AnnotationOut, status_code=status.HTTP_201_CREATED)
def annotate_event(event_id: str, request: AnnotationCreate, db: Session = Depends(get_db)) -> Annotation:
    event = db.get(PayloadEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    annotation = Annotation(event_id=event_id, **request.model_dump())
    db.add(annotation)
    if request.review_status == "confirmed":
        event.verdict = request.label
    db.commit()
    db.refresh(annotation)
    return annotation

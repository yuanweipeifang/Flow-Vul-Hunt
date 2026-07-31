from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..audit import audit_log
from ..database import get_db
from ..models import SavedHuntQuery
from ..schemas import HuntRequest, HuntResult, SavedHuntQueryCreate, SavedHuntQueryOut, SavedHuntRunResult
from ..services.event_mapper import event_summary
from ..services.hunt_service import execute_hunt, interpret_hunt
from ..security import Actor, get_actor, require_roles


router = APIRouter(prefix="/hunt", tags=["hunting"])


@router.post("/query", response_model=HuntResult)
def hunt(
    request: HuntRequest,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> HuntResult:
    filters, llm_used, warning = interpret_hunt(request.query, request.use_llm)
    events, stats = execute_hunt(db, filters, request.dataset_id, request.limit, request.exclude_suppressed)
    suppression_text = "已排除判定为 benign 的事件。" if request.exclude_suppressed else None
    return HuntResult(
        interpreted_filters=filters.model_dump(exclude_none=True),
        events=[event_summary(event) for event in events],
        summary=f"查询基于实际数据库返回 {len(events)} 条事件，排除 {stats['suppressed_events']} 条 benign 事件。",
        llm_used=llm_used,
        warning=warning,
        matched_events=stats["matched_events"],
        suppressed_events=stats["suppressed_events"],
        suppression_policy=suppression_text,
    )


@router.post("/saved", response_model=SavedHuntQueryOut, status_code=status.HTTP_201_CREATED)
def save_hunt_query(
    request: SavedHuntQueryCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_roles("admin", "analyst")),
) -> SavedHuntQuery:
    filters, llm_used, warning = interpret_hunt(request.query, request.use_llm)
    saved = SavedHuntQuery(
        name=request.name,
        query=request.query,
        dataset_id=request.dataset_id,
        filters={
            **filters.model_dump(exclude_none=True),
            "use_llm": request.use_llm,
            "llm_used": llm_used,
            "exclude_suppressed": request.exclude_suppressed,
            "limit": request.limit,
            "warning": warning,
        },
        tags=request.tags,
        created_by=actor.name,
    )
    db.add(saved)
    audit_log(db, "hunt_query.save", "saved_hunt_query", saved.id, {"name": request.name})
    db.commit()
    db.refresh(saved)
    return saved


@router.get("/saved", response_model=list[SavedHuntQueryOut])
def list_saved_hunt_queries(
    dataset_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> list[SavedHuntQuery]:
    from sqlalchemy import select

    statement = select(SavedHuntQuery)
    if dataset_id:
        statement = statement.where(SavedHuntQuery.dataset_id == dataset_id)
    return list(db.scalars(statement.order_by(SavedHuntQuery.updated_at.desc()).limit(limit)).all())


@router.post("/saved/{query_id}/run", response_model=SavedHuntRunResult)
def run_saved_hunt_query(
    query_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> SavedHuntRunResult:
    saved = db.get(SavedHuntQuery, query_id)
    if not saved:
        raise HTTPException(status_code=404, detail="saved hunt query not found")
    filters, llm_used, warning = interpret_hunt(saved.query, bool(saved.filters.get("use_llm", True)))
    limit = int(saved.filters.get("limit", 50))
    exclude_suppressed = bool(saved.filters.get("exclude_suppressed", True))
    events, stats = execute_hunt(db, filters, saved.dataset_id, limit, exclude_suppressed)
    saved.filters = {
        **filters.model_dump(exclude_none=True),
        "use_llm": bool(saved.filters.get("use_llm", True)),
        "llm_used": llm_used,
        "exclude_suppressed": exclude_suppressed,
        "limit": limit,
        "warning": warning,
    }
    saved.last_run_summary = {
        "returned_events": len(events),
        "matched_events": stats["matched_events"],
        "suppressed_events": stats["suppressed_events"],
    }
    audit_log(db, "hunt_query.run", "saved_hunt_query", saved.id, saved.last_run_summary)
    db.commit()
    db.refresh(saved)
    result = HuntResult(
        interpreted_filters=filters.model_dump(exclude_none=True),
        events=[event_summary(event) for event in events],
        summary=f"保存查询返回 {len(events)} 条事件，排除 {stats['suppressed_events']} 条 benign 事件。",
        llm_used=llm_used,
        warning=warning,
        matched_events=stats["matched_events"],
        suppressed_events=stats["suppressed_events"],
        suppression_policy="已排除判定为 benign 的事件。" if exclude_suppressed else None,
    )
    return SavedHuntRunResult(saved_query=saved, result=result)

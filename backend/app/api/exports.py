from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Dataset, Incident, PayloadEvent
from ..services.export_service import stream_events_csv, stream_events_json, stream_incidents_json
from ..security import Actor, get_actor

router = APIRouter(prefix="/exports", tags=["exports"])


def _require_dataset(db: Session, dataset_id: str) -> None:
    if not db.get(Dataset, dataset_id):
        raise HTTPException(status_code=404, detail="dataset not found")


@router.get("/events")
def export_events(
    dataset_id: str,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    min_risk: float | None = Query(default=None, ge=0, le=100),
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
):
    _require_dataset(db, dataset_id)
    statement = select(PayloadEvent).where(PayloadEvent.dataset_id == dataset_id)
    if min_risk is not None:
        statement = statement.where(PayloadEvent.risk_score >= min_risk)
    events = db.scalars(statement.order_by(PayloadEvent.row_number)).yield_per(500)
    if format == "json":
        return StreamingResponse(
            stream_events_json(events),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="events-{dataset_id}.json"'},
        )
    return StreamingResponse(
        stream_events_csv(events),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="events-{dataset_id}.csv"'},
    )


@router.get("/incidents")
def export_incidents(
    dataset_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
):
    _require_dataset(db, dataset_id)
    incidents = db.scalars(
        select(Incident).where(Incident.dataset_id == dataset_id).order_by(Incident.risk_score.desc())
    ).yield_per(200)
    return StreamingResponse(
        stream_incidents_json(incidents),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="incidents-{dataset_id}.json"'},
    )

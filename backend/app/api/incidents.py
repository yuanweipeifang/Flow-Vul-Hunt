from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..audit import audit_log
from ..database import get_db
from ..models import Dataset, Incident, IncidentReport
from ..schemas import IncidentOut, IncidentReportOut, IncidentUpdate, ReportGenerateRequest
from ..services.incident_service import rebuild_incidents
from ..services.report_service import generate_report
from ..security import Actor, get_actor, require_roles


router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    dataset_id: str | None = None,
    incident_status: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    assignee: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> list[Incident]:
    statement = select(Incident).options(selectinload(Incident.event_links))
    if dataset_id:
        statement = statement.where(Incident.dataset_id == dataset_id)
    if incident_status:
        statement = statement.where(Incident.status == incident_status)
    if severity:
        statement = statement.where(Incident.severity == severity)
    if assignee:
        statement = statement.where(Incident.assignee == assignee)
    return list(db.scalars(statement.order_by(Incident.risk_score.desc()).limit(limit)).all())


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, db: Session = Depends(get_db), _actor: Actor = Depends(get_actor)) -> Incident:
    incident = db.scalar(
        select(Incident).where(Incident.id == incident_id).options(selectinload(Incident.event_links))
    )
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident


@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(
    incident_id: str,
    request: IncidentUpdate,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> Incident:
    incident = db.scalar(
        select(Incident).where(Incident.id == incident_id).options(selectinload(Incident.event_links))
    )
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    changes = request.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(incident, field, value)
    if "status" in changes:
        incident.closed_at = datetime.now(timezone.utc) if incident.status in {"resolved", "closed"} else None
    audit_log(db, "incident.update", "incident", incident_id, changes)
    db.commit()
    db.refresh(incident)
    return incident


@router.post("/rebuild/{dataset_id}", response_model=list[IncidentOut])
def rebuild(
    dataset_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> list[Incident]:
    if not db.get(Dataset, dataset_id):
        raise HTTPException(status_code=404, detail="dataset not found")
    rebuild_incidents(db, dataset_id)
    audit_log(db, "incident.rebuild", "dataset", dataset_id)
    db.commit()
    return list(
        db.scalars(
            select(Incident).where(Incident.dataset_id == dataset_id).options(selectinload(Incident.event_links))
        ).all()
    )


@router.post("/{incident_id}/reports", response_model=IncidentReportOut)
def create_report(
    incident_id: str,
    request: ReportGenerateRequest,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> IncidentReport:
    try:
        report = generate_report(db, incident_id, request.use_llm)
        audit_log(db, "report.generate", "incident", incident_id, {"report_id": report.id})
        db.commit()
        db.refresh(report)
        return report
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{incident_id}/reports", response_model=list[IncidentReportOut])
def list_reports(
    incident_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> list[IncidentReport]:
    if not db.get(Incident, incident_id):
        raise HTTPException(status_code=404, detail="incident not found")
    return list(
        db.scalars(
            select(IncidentReport)
            .where(IncidentReport.incident_id == incident_id)
            .order_by(IncidentReport.created_at.desc())
        ).all()
    )

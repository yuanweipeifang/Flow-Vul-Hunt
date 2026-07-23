from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AnalysisJob, Dataset, DetectionFinding, Incident, PayloadEvent


def _grouped_counts(db: Session, field, *conditions) -> dict[str, int]:
    statement = select(field, func.count()).where(*conditions).group_by(field)
    return {str(key or "unknown"): int(value) for key, value in db.execute(statement).all()}


def dashboard_overview(db: Session, dataset_id: str | None = None) -> dict:
    event_conditions = (PayloadEvent.dataset_id == dataset_id,) if dataset_id else ()
    incident_conditions = (Incident.dataset_id == dataset_id,) if dataset_id else ()
    dataset_conditions = (Dataset.id == dataset_id,) if dataset_id else ()
    job_conditions = (AnalysisJob.dataset_id == dataset_id,) if dataset_id else ()

    event_count = db.scalar(select(func.count()).select_from(PayloadEvent).where(*event_conditions)) or 0
    finding_count = db.scalar(
        select(func.count()).select_from(DetectionFinding).join(PayloadEvent).where(*event_conditions)
    ) or 0
    incident_count = db.scalar(select(func.count()).select_from(Incident).where(*incident_conditions)) or 0
    dataset_count = db.scalar(select(func.count()).select_from(Dataset).where(*dataset_conditions)) or 0
    job_count = db.scalar(select(func.count()).select_from(AnalysisJob).where(*job_conditions)) or 0
    average_risk = db.scalar(select(func.avg(PayloadEvent.risk_score)).where(*event_conditions)) or 0.0
    maximum_risk = db.scalar(select(func.max(PayloadEvent.risk_score)).where(*event_conditions)) or 0.0

    attack_statement = (
        select(DetectionFinding.attack_type, func.count())
        .join(PayloadEvent)
        .where(DetectionFinding.attack_type != "risk_assessment", *event_conditions)
        .group_by(DetectionFinding.attack_type)
        .order_by(func.count().desc())
        .limit(10)
    )
    return {
        "totals": {
            "datasets": int(dataset_count),
            "events": int(event_count),
            "findings": int(finding_count),
            "incidents": int(incident_count),
            "jobs": int(job_count),
        },
        "datasets_by_status": _grouped_counts(db, Dataset.status, *dataset_conditions),
        "events_by_verdict": _grouped_counts(db, PayloadEvent.verdict, *event_conditions),
        "incidents_by_severity": _grouped_counts(db, Incident.severity, *incident_conditions),
        "incidents_by_status": _grouped_counts(db, Incident.status, *incident_conditions),
        "top_attack_types": {str(key): int(value) for key, value in db.execute(attack_statement).all()},
        "risk": {"average": round(float(average_risk), 2), "maximum": round(float(maximum_risk), 2)},
    }

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import DetectionFinding, PayloadEvent


def _event_count(db: Session, dataset_id: str) -> int:
    return db.scalar(select(func.count()).select_from(PayloadEvent).where(PayloadEvent.dataset_id == dataset_id)) or 0


def _string_set(db: Session, dataset_id: str, column) -> set[str]:
    return {
        value
        for value in db.scalars(
            select(column).where(PayloadEvent.dataset_id == dataset_id, column.is_not(None)).distinct()
        ).all()
        if value
    }


def _attack_types(db: Session, dataset_id: str) -> set[str]:
    return {
        value
        for value in db.scalars(
            select(DetectionFinding.attack_type)
            .join(PayloadEvent, PayloadEvent.id == DetectionFinding.event_id)
            .where(PayloadEvent.dataset_id == dataset_id, DetectionFinding.detector_type != "risk")
            .distinct()
        ).all()
        if value
    }


def compare_datasets(db: Session, baseline_dataset_id: str, candidate_dataset_id: str) -> dict:
    baseline_hashes = _string_set(db, baseline_dataset_id, PayloadEvent.payload_hash)
    candidate_hashes = _string_set(db, candidate_dataset_id, PayloadEvent.payload_hash)
    baseline_hosts = {item.lower() for item in _string_set(db, baseline_dataset_id, PayloadEvent.host)}
    candidate_hosts = {item.lower() for item in _string_set(db, candidate_dataset_id, PayloadEvent.host)}
    baseline_paths = _string_set(db, baseline_dataset_id, PayloadEvent.path)
    candidate_paths = _string_set(db, candidate_dataset_id, PayloadEvent.path)
    baseline_attacks = _attack_types(db, baseline_dataset_id)
    candidate_attacks = _attack_types(db, candidate_dataset_id)
    baseline_avg = db.scalar(
        select(func.avg(PayloadEvent.risk_score)).where(PayloadEvent.dataset_id == baseline_dataset_id)
    ) or 0.0
    candidate_avg = db.scalar(
        select(func.avg(PayloadEvent.risk_score)).where(PayloadEvent.dataset_id == candidate_dataset_id)
    ) or 0.0
    return {
        "baseline_dataset_id": baseline_dataset_id,
        "candidate_dataset_id": candidate_dataset_id,
        "counts": {
            "baseline_events": _event_count(db, baseline_dataset_id),
            "candidate_events": _event_count(db, candidate_dataset_id),
            "new_payload_hashes": len(candidate_hashes - baseline_hashes),
            "repeated_payload_hashes": len(candidate_hashes & baseline_hashes),
        },
        "risk": {
            "baseline_average": round(float(baseline_avg), 2),
            "candidate_average": round(float(candidate_avg), 2),
            "average_delta": round(float(candidate_avg) - float(baseline_avg), 2),
        },
        "new_hosts": sorted(candidate_hosts - baseline_hosts)[:100],
        "new_paths": sorted(candidate_paths - baseline_paths)[:100],
        "new_attack_types": sorted(candidate_attacks - baseline_attacks),
        "repeated_payload_hashes": sorted(candidate_hashes & baseline_hashes)[:100],
    }

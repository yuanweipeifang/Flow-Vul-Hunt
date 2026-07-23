from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import DetectionFinding, Incident, IncidentEvent, PayloadEvent
from ..risk.scoring import severity_for_score


def rebuild_incidents(db: Session, dataset_id: str) -> list[Incident]:
    existing_ids = db.scalars(select(Incident.id).where(Incident.dataset_id == dataset_id)).all()
    if existing_ids:
        db.execute(delete(Incident).where(Incident.id.in_(existing_ids)))

    rows = db.execute(
        select(PayloadEvent, DetectionFinding)
        .join(DetectionFinding, DetectionFinding.event_id == PayloadEvent.id)
        .where(PayloadEvent.dataset_id == dataset_id, PayloadEvent.risk_score >= 25)
    ).all()
    groups: dict[tuple[str, str], dict[str, PayloadEvent]] = defaultdict(dict)
    for event, finding in rows:
        host_key = (event.host or "unknown-host").lower()
        groups[(host_key, finding.attack_type)][event.id] = event

    incidents: list[Incident] = []
    for (host, attack_type), event_map in groups.items():
        events = sorted(event_map.values(), key=lambda item: item.row_number)
        if len(events) < 2:
            continue
        max_risk = max(event.risk_score for event in events)
        risk = round(min(100.0, max_risk + min(10, len(events) - 1)), 1)
        incident = Incident(
            dataset_id=dataset_id,
            title=f"{host} 的 {attack_type} Payload 活动簇",
            incident_type="payload_activity_cluster",
            summary=f"基于实际数据发现 {len(events)} 条具有相同 Host 和攻击类型的关联 Payload。",
            risk_score=risk,
            severity=severity_for_score(risk),
            is_simulated=False,
        )
        db.add(incident)
        db.flush()
        for order, event in enumerate(events):
            db.add(
                IncidentEvent(
                    incident_id=incident.id,
                    event_id=event.id,
                    relation_type="same_host_and_attack_type",
                    evidence={"host": host, "attack_type": attack_type},
                    sort_order=order,
                )
            )
        incidents.append(incident)
    db.commit()
    return incidents


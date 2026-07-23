from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator

from ..models import Incident, PayloadEvent


def _csv_line(values: list[object]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerow(values)
    return buffer.getvalue()


def stream_events_csv(events: Iterable[PayloadEvent]) -> Iterator[str]:
    yield "\ufeff" + _csv_line([
        "id", "dataset_id", "row_number", "protocol", "method", "host", "path",
        "verdict", "risk_score", "parse_status", "is_binary", "payload_hash",
    ])
    for event in events:
        yield _csv_line([
            event.id, event.dataset_id, event.row_number, event.protocol, event.http_method,
            event.host, event.path, event.verdict, event.risk_score, event.parse_status,
            event.is_binary, event.payload_hash,
        ])


def stream_events_json(events: Iterable[PayloadEvent]) -> Iterator[str]:
    yield "["
    first = True
    for event in events:
        if not first:
            yield ","
        first = False
        yield json.dumps({
            "id": event.id,
            "dataset_id": event.dataset_id,
            "row_number": event.row_number,
            "protocol": event.protocol,
            "http_method": event.http_method,
            "host": event.host,
            "path": event.path,
            "verdict": event.verdict,
            "risk_score": event.risk_score,
            "parse_status": event.parse_status,
            "is_binary": event.is_binary,
            "payload_hash": event.payload_hash,
        }, ensure_ascii=False)
    yield "]"


def stream_incidents_json(incidents: Iterable[Incident]) -> Iterator[str]:
    yield "["
    first = True
    for incident in incidents:
        if not first:
            yield ","
        first = False
        yield json.dumps({
            "id": incident.id,
            "dataset_id": incident.dataset_id,
            "title": incident.title,
            "incident_type": incident.incident_type,
            "summary": incident.summary,
            "risk_score": incident.risk_score,
            "severity": incident.severity,
            "status": incident.status,
            "assignee": incident.assignee,
            "resolution": incident.resolution,
        }, ensure_ascii=False)
    yield "]"

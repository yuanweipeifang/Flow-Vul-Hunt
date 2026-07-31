from __future__ import annotations

from ..models import PayloadEvent


def event_summary(event: PayloadEvent) -> dict:
    return {
        "id": event.id,
        "dataset_id": event.dataset_id,
        "row_number": event.row_number,
        "protocol": event.protocol,
        "http_method": event.http_method,
        "host": event.host,
        "path": event.path,
        "payload_length": event.payload_length,
        "is_binary": event.is_binary,
        "parse_status": event.parse_status,
        "verdict": event.verdict,
        "risk_score": event.risk_score,
        "created_at": event.created_at,
    }


def event_detail(event: PayloadEvent) -> dict:
    return {
        **event_summary(event),
        "raw_payload": event.raw_payload,
        "decoded_payload": event.decoded_payload,
        "payload_hash": event.payload_hash,
        "query": event.query,
        "headers": event.headers,
        "body": event.body,
        "content_type": event.content_type,
        "entropy": event.entropy,
        "printable_ratio": event.printable_ratio,
        "encoded_segment_count": event.encoded_segment_count,
        "parse_error": event.parse_error,
        "findings": event.findings,
        "llm_analyses": event.llm_analyses,
    }

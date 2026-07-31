from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from ..config import get_settings
from ..ingestion.csv_reader import read_single_column_csv
from ..ingestion.payload_parser import parse_payload
from ..models import Dataset, PayloadEvent


def ingest_dataset(db: Session, filename: str, name: str | None, content: bytes) -> Dataset:
    settings = get_settings()
    payloads = read_single_column_csv(content, settings.max_payload_chars)
    dataset = Dataset(
        name=(name or filename).strip()[:255],
        filename=filename[:255],
        file_sha256=hashlib.sha256(content).hexdigest(),
        status="parsing",
        row_count=len(payloads),
    )
    db.add(dataset)
    db.flush()

    parsed_count = 0
    failed_count = 0
    try:
        batch_size = max(settings.ingest_batch_size, 1)
        for row_number, raw in enumerate(payloads, start=1):
            parsed = parse_payload(raw)
            event = PayloadEvent(
                dataset_id=dataset.id,
                row_number=row_number,
                raw_payload=parsed.raw_payload,
                decoded_payload=parsed.decoded_payload,
                payload_hash=parsed.payload_hash,
                protocol=parsed.protocol,
                http_method=parsed.http_method,
                host=parsed.host,
                path=parsed.path,
                query=parsed.query,
                headers=parsed.headers,
                body=parsed.body,
                content_type=parsed.content_type,
                payload_length=parsed.payload_length,
                entropy=parsed.entropy,
                printable_ratio=parsed.printable_ratio,
                encoded_segment_count=parsed.encoded_segment_count,
                is_binary=parsed.is_binary,
                parse_status=parsed.parse_status,
                parse_error=parsed.parse_error,
            )
            db.add(event)
            if parsed.parse_status == "failed":
                failed_count += 1
            else:
                parsed_count += 1
            if row_number % batch_size == 0:
                db.flush()
        dataset.parsed_count = parsed_count
        dataset.failed_count = failed_count
        dataset.status = "ready"
        db.commit()
        db.refresh(dataset)
        return dataset
    except Exception:
        db.rollback()
        raise

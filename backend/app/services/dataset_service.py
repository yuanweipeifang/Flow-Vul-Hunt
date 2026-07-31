from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ..config import BASE_DIR, get_settings
from ..ingestion.csv_reader import read_single_column_csv
from ..ingestion.payload_parser import parse_payload
from ..models import Dataset, PayloadEvent


def csv_storage_root() -> Path:
    settings = get_settings()
    root = Path(settings.csv_storage_dir).expanduser()
    if not root.is_absolute():
        root = BASE_DIR / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def safe_csv_filename(filename: str) -> str:
    raw = Path(filename or "dataset.csv").name.strip() or "dataset.csv"
    stem = Path(raw).stem.strip() or "dataset"
    suffix = Path(raw).suffix.lower() or ".csv"
    if suffix != ".csv":
        suffix = ".csv"
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" ._") or "dataset"
    return f"{stem[:180]}{suffix}"


def store_csv_upload(filename: str, content: bytes) -> Path:
    root = csv_storage_root()
    safe_name = safe_csv_filename(filename)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stored_name = f"{stamp}_{uuid4().hex[:8]}_{safe_name}"
    path = root / stored_name
    path.write_bytes(content)
    return path


def ensure_dataset_storage_column(db: Session) -> None:
    columns = {column["name"] for column in inspect(db.bind).get_columns("datasets")}
    if "storage_path" not in columns:
        db.execute(text("ALTER TABLE datasets ADD COLUMN storage_path TEXT"))
        db.commit()


def ingest_dataset(db: Session, filename: str, name: str | None, content: bytes, storage_path: str | None = None) -> Dataset:
    ensure_dataset_storage_column(db)
    settings = get_settings()
    payloads = read_single_column_csv(content, settings.max_payload_chars)
    dataset = Dataset(
        name=(name or filename).strip()[:255],
        filename=filename[:255],
        file_sha256=hashlib.sha256(content).hexdigest(),
        storage_path=storage_path,
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

from __future__ import annotations

import csv
import io


class DatasetFormatError(ValueError):
    pass


def read_single_column_csv(content: bytes, max_payload_chars: int) -> list[str]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("utf-8-sig", errors="replace")

    reader = csv.reader(io.StringIO(text, newline=""), strict=False)
    payloads: list[str] = []
    for row_number, row in enumerate(reader, start=1):
        if not row or all(not value for value in row):
            continue
        if len(row) != 1:
            raise DatasetFormatError(
                f"row {row_number} has {len(row)} columns; expected a headerless single-column CSV"
            )
        payload = row[0]
        if len(payload) > max_payload_chars:
            raise DatasetFormatError(
                f"row {row_number} exceeds MAX_PAYLOAD_CHARS ({max_payload_chars})"
            )
        payloads.append(payload)
    if not payloads:
        raise DatasetFormatError("CSV contains no payload rows")
    return payloads


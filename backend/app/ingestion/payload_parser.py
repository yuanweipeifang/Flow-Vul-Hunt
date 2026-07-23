from __future__ import annotations

import hashlib
import math
import re
import string
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


HEX_ESCAPE = re.compile(r"\\([0-9A-Fa-f]{2})")
HTTP_REQUEST = re.compile(r"^([A-Z]{2,16})\s+(\S+)\s+HTTP/(\d(?:\.\d)?)$")
ENCODING_MARKERS = re.compile(r"(?:%[0-9A-Fa-f]{2}|\\[0-9A-Fa-f]{2}|&#(?:x[0-9A-Fa-f]+|\d+);)")


@dataclass(slots=True)
class ParsedPayload:
    raw_payload: str
    decoded_payload: str
    payload_hash: str
    protocol: str = "unknown"
    http_method: str | None = None
    host: str | None = None
    path: str | None = None
    query: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    content_type: str | None = None
    payload_length: int = 0
    entropy: float = 0.0
    printable_ratio: float = 0.0
    encoded_segment_count: int = 0
    is_binary: bool = False
    parse_status: str = "success"
    parse_error: str | None = None


def _decode_hex_escapes(value: str) -> tuple[bytes, int]:
    output = bytearray()
    count = 0
    index = 0
    while index < len(value):
        if index + 2 < len(value) and value[index] == "\\" and all(
            char in string.hexdigits for char in value[index + 1:index + 3]
        ):
            output.append(int(value[index + 1:index + 3], 16))
            count += 1
            index += 3
            continue
        output.extend(value[index].encode("utf-8", errors="replace"))
        index += 1
    return bytes(output), count


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _printable_ratio(data: bytes) -> float:
    if not data:
        return 1.0
    printable = sum(byte in b"\r\n\t" or 32 <= byte <= 126 for byte in data)
    return printable / len(data)


def _safe_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="backslashreplace")


def _split_http(text: str) -> tuple[str, dict[str, str], str]:
    if "\r\n" in text:
        lines = text.split("\r\n")
    else:
        lines = text.split("\n")
    request_line = lines[0].strip() if lines else ""
    headers: dict[str, str] = {}
    body_start = len(lines)
    for index, line in enumerate(lines[1:], start=1):
        if line == "":
            body_start = index + 1
            break
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        normalized = name.strip().lower()
        if normalized:
            headers[normalized] = value.strip()
    return request_line, headers, "\r\n".join(lines[body_start:])


def parse_payload(raw_payload: str) -> ParsedPayload:
    raw = raw_payload.lstrip("\ufeff")
    raw_bytes = raw.encode("utf-8", errors="replace")
    decoded_bytes, hex_count = _decode_hex_escapes(raw)
    ratio = _printable_ratio(decoded_bytes)
    entropy = _entropy(decoded_bytes)
    decoded = _safe_text(decoded_bytes)
    result = ParsedPayload(
        raw_payload=raw_payload,
        decoded_payload=decoded,
        payload_hash=hashlib.sha256(raw_bytes).hexdigest(),
        payload_length=len(decoded_bytes),
        entropy=round(entropy, 4),
        printable_ratio=round(ratio, 4),
        encoded_segment_count=hex_count + len(ENCODING_MARKERS.findall(raw)),
        is_binary=ratio < 0.72 or "application/octet-stream" in decoded.lower(),
    )

    try:
        request_line, headers, body = _split_http(decoded)
        match = HTTP_REQUEST.match(request_line)
        if not match:
            result.parse_status = "partial"
            result.parse_error = "HTTP request line not recognized"
            return result
        method, target, _version = match.groups()
        split_target = urlsplit(target)
        result.protocol = "http"
        result.http_method = method
        result.host = headers.get("host") or split_target.hostname
        result.path = unquote(split_target.path or "/")
        result.query = unquote(split_target.query) if split_target.query else None
        result.headers = headers
        result.body = body or None
        result.content_type = headers.get("content-type")
        return result
    except Exception as exc:  # Defensive: malformed payloads must still be persisted.
        result.parse_status = "failed"
        result.parse_error = f"{type(exc).__name__}: {exc}"
        return result


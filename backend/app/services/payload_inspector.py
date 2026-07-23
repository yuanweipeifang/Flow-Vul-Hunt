from __future__ import annotations

import base64
import binascii
import html
from urllib.parse import unquote_plus

from ..ingestion.payload_parser import parse_payload


def _try_base64(value: str) -> str | None:
    compact = "".join(value.split())
    if len(compact) < 8 or len(compact) % 4:
        return None
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError:
        return decoded.decode("utf-8", errors="backslashreplace")


def inspect_payload(payload: str) -> dict:
    parsed = parse_payload(payload)
    url_decoded_once = unquote_plus(parsed.decoded_payload)
    url_decoded_twice = unquote_plus(url_decoded_once)
    html_unescaped = html.unescape(parsed.decoded_payload)
    variants = {
        "hex_escape_decoded": parsed.decoded_payload,
        "url_decoded_once": url_decoded_once,
        "url_decoded_twice": url_decoded_twice if url_decoded_twice != url_decoded_once else None,
        "html_unescaped": html_unescaped if html_unescaped != parsed.decoded_payload else None,
        "base64_decoded": _try_base64(parsed.body or parsed.query or parsed.decoded_payload),
    }
    warnings: list[str] = []
    if parsed.parse_status != "success":
        warnings.append(parsed.parse_error or "payload was only partially parsed")
    if parsed.is_binary:
        warnings.append("payload appears to contain binary or low-printable content")
    if parsed.encoded_segment_count:
        warnings.append(f"payload contains {parsed.encoded_segment_count} encoded segments")
    return {
        "parsed": {
            "protocol": parsed.protocol,
            "http_method": parsed.http_method,
            "host": parsed.host,
            "path": parsed.path,
            "query": parsed.query,
            "headers": parsed.headers,
            "body": parsed.body,
            "content_type": parsed.content_type,
            "payload_hash": parsed.payload_hash,
            "payload_length": parsed.payload_length,
            "entropy": parsed.entropy,
            "printable_ratio": parsed.printable_ratio,
            "encoded_segment_count": parsed.encoded_segment_count,
            "is_binary": parsed.is_binary,
            "parse_status": parsed.parse_status,
            "parse_error": parsed.parse_error,
        },
        "decoded_variants": variants,
        "warnings": warnings,
    }

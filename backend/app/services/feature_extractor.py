from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from ..models import PayloadEvent


DANGEROUS_PARAM_NAMES = {
    "cmd", "command", "exec", "shell", "query", "sql", "id", "file", "path", "template",
    "url", "uri", "redirect", "next", "callback", "target", "dest", "return", "upload",
}
SINK_PATTERNS = {
    "command_execution": re.compile(r"(?:shell_exec|passthru|system\s*\(|exec\s*\(|/bin/(?:sh|bash)|cmd=)", re.I),
    "sql_execution": re.compile(r"(?:union\s+select|select\s+.+\s+from|sleep\s*\(|benchmark\s*\()", re.I | re.S),
    "template_expression": re.compile(r"(?:#\{|\$\{|\{\{|\{%|freemarker|velocity|ognl)", re.I),
    "jndi_lookup": re.compile(r"\$\{\s*jndi\s*:", re.I),
    "webshell_keyword": re.compile(r"(?:eval\s*\(|assert\s*\(|base64_decode\s*\(|antsword|behinder|godzilla)", re.I),
    "deserialization_marker": re.compile(r"(?:@type|java\.rmi|ysoserial|rO0AB|rememberMe=)", re.I),
}
FRAMEWORK_PATTERNS = {
    "log4j": re.compile(r"\$\{\s*jndi\s*:", re.I),
    "struts2": re.compile(r"(?:struts|ognl|%23_memberAccess|redirectAction)", re.I),
    "spring": re.compile(r"(?:spring|actuator|spel|T\(java\.lang\.Runtime\))", re.I),
    "fastjson": re.compile(r"(?:\"@type\"|%22@type%22|fastjson)", re.I),
    "shiro": re.compile(r"(?:rememberMe=|shiro)", re.I),
    "php": re.compile(r"(?:phpinfo|\.php|eval\s*\(|assert\s*\()", re.I),
}
SENSITIVE_PATH_PATTERNS = {
    "linux_password_file": re.compile(r"/etc/passwd", re.I),
    "linux_proc": re.compile(r"/proc/self", re.I),
    "windows_ini": re.compile(r"windows/win\.ini", re.I),
    "env_file": re.compile(r"/\.env(?:\?|$|/)", re.I),
    "git_metadata": re.compile(r"/\.git(?:/|$)", re.I),
    "spring_actuator": re.compile(r"/actuator(?:/|$)", re.I),
}
INTERNAL_HOST_PATTERNS = (
    re.compile(r"^(?:127\.|10\.|localhost$|0\.0\.0\.0$)", re.I),
    re.compile(r"^192\.168\."),
    re.compile(r"^172\.(?:1[6-9]|2\d|3[0-1])\."),
    re.compile(r"^169\.254\.169\.254$"),
    re.compile(r"^(?:\[?::1\]?)$"),
)


def _truncate(value: str | None, limit: int = 200) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[:limit] + "[TRUNCATED]"


def _query_params(query: str | None) -> list[dict]:
    if not query:
        return []
    return [
        {"source": "query", "name": name, "value_preview": _truncate(value)}
        for name, value in parse_qsl(query, keep_blank_values=True)
    ]


def _body_params(body: str | None, content_type: str | None) -> list[dict]:
    if not body:
        return []
    lowered = (content_type or "").lower()
    if "application/x-www-form-urlencoded" in lowered:
        return [
            {"source": "body_form", "name": name, "value_preview": _truncate(value)}
            for name, value in parse_qsl(body, keep_blank_values=True)
        ]
    if body.lstrip().startswith("{"):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            return [
                {"source": "body_json", "name": str(name), "value_preview": _truncate(str(value))}
                for name, value in data.items()
            ]
    return []


def _classify_value(value: str | None) -> list[str]:
    if value is None:
        return []
    decoded = unquote_plus(value)
    labels: list[str] = []
    if re.search(r"https?://", decoded, re.I):
        labels.append("url")
    if any(pattern.search(urlsplit(decoded).hostname or decoded) for pattern in INTERNAL_HOST_PATTERNS):
        labels.append("internal_endpoint")
    if re.search(r"(?:\.\./|\.\.\\|%2e%2e)", value, re.I):
        labels.append("path_traversal")
    if re.search(r"(?:<script|javascript:|onerror=|onload=)", decoded, re.I):
        labels.append("xss_payload")
    if re.search(r"(?:\bunion\s+select\b|\bor\s+1=1\b|sleep\s*\()", decoded, re.I):
        labels.append("sql_payload")
    return sorted(set(labels))


def _urls(text: str) -> list[dict]:
    items = []
    for match in re.finditer(r"https?://[^\s'\"<>]+", text, re.I):
        raw = match.group(0)
        split = urlsplit(raw)
        host = (split.hostname or "").lower()
        items.append({
            "url": _truncate(raw, 300),
            "host": host,
            "is_internal": any(pattern.search(host) for pattern in INTERNAL_HOST_PATTERNS),
        })
    return items[:20]


def extract_event_features(event: PayloadEvent) -> dict:
    decoded = event.decoded_payload or ""
    parameters = _query_params(event.query) + _body_params(event.body, event.content_type)
    for parameter in parameters:
        parameter["name_is_sensitive"] = parameter["name"].lower() in DANGEROUS_PARAM_NAMES
        parameter["value_kinds"] = _classify_value(parameter.get("value_preview"))

    split_path = event.path or "/"
    extension = split_path.rsplit(".", 1)[1].lower() if "." in split_path.rsplit("/", 1)[-1] else None
    double_decoded = unquote_plus(unquote_plus(decoded))
    callback_urls = _urls(decoded)
    internal_parameter_endpoints = [
        {
            "source": parameter["source"],
            "parameter": parameter["name"],
            "value_preview": parameter.get("value_preview"),
            "is_internal": True,
        }
        for parameter in parameters
        if "internal_endpoint" in parameter.get("value_kinds", [])
    ]
    sensitive_paths = [
        name for name, pattern in SENSITIVE_PATH_PATTERNS.items()
        if pattern.search(decoded) or pattern.search(split_path)
    ]
    sinks = [
        {"type": name, "fragment": _truncate(match.group(0), 160)}
        for name, pattern in SINK_PATTERNS.items()
        for match in [pattern.search(decoded)]
        if match
    ]
    frameworks = [
        name for name, pattern in FRAMEWORK_PATTERNS.items()
        if pattern.search(decoded) or pattern.search(split_path)
    ]
    return {
        "path": {
            "value": split_path,
            "segments": [segment for segment in split_path.split("/") if segment],
            "extension": extension,
            "depth": len([segment for segment in split_path.split("/") if segment]),
        },
        "parameters": parameters,
        "parameter_names": sorted({parameter["name"] for parameter in parameters}),
        "dangerous_parameter_names": sorted(
            {parameter["name"] for parameter in parameters if parameter["name"].lower() in DANGEROUS_PARAM_NAMES}
        ),
        "headers": {
            "names": sorted((event.headers or {}).keys()),
            "content_type": event.content_type,
            "has_cookie": "cookie" in (event.headers or {}),
            "has_authorization": "authorization" in (event.headers or {}),
        },
        "encoding": {
            "encoded_segment_count": event.encoded_segment_count,
            "double_url_decoded_changes": double_decoded != decoded,
            "html_entity_count": len(re.findall(r"&#(?:x[0-9A-Fa-f]+|\d+);", decoded)),
            "is_binary": event.is_binary,
            "entropy": event.entropy,
        },
        "callback_urls": callback_urls,
        "internal_endpoints": [
            *[item for item in callback_urls if item["is_internal"]],
            *internal_parameter_endpoints,
        ],
        "sensitive_paths": sensitive_paths,
        "dangerous_sinks": sinks,
        "framework_fingerprints": sorted(set(frameworks)),
        "file_upload_indicators": {
            "multipart": "multipart/form-data" in (event.content_type or "").lower(),
            "filename_marker": bool(re.search(r'filename\s*=', decoded, re.I)),
        },
    }

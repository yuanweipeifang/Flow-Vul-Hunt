from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ..models import AuthorizedTarget, ValidationResult, ValidationRun, VulnerabilityCandidate


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SENSITIVE_VALUE = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|session|cookie)=([^&\s]+)")


class ValidationPolicyError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def normalize_path(path: str | None) -> str:
    value = (path or "/").strip() or "/"
    return value if value.startswith("/") else f"/{value}"


def target_allows_path(target: AuthorizedTarget, path: str) -> bool:
    scope = normalize_path(target.path_scope)
    candidate = normalize_path(path).split("?", 1)[0]
    return candidate == scope.rstrip("/") or candidate.startswith(scope.rstrip("/") + "/") or scope == "/"


def _url(target: AuthorizedTarget, path: str) -> str:
    port = "" if target.port in {None, default_port(target.scheme)} else f":{target.port}"
    return f"{target.scheme}://{target.host}{port}{normalize_path(path).split('?', 1)[0]}"


def _redact(value: str) -> str:
    return SENSITIVE_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def _response_summary(response: httpx.Response) -> dict:
    text = response.text if response.request.method == "GET" else ""
    preview = _redact(text[:300]) if text else None
    return {
        "status_code": response.status_code,
        "headers": {
            key.lower(): value[:200]
            for key, value in response.headers.items()
            if key.lower() in {"content-type", "server", "location", "x-powered-by"}
        },
        "body_preview": preview,
        "body_sha256": hashlib.sha256(response.content).hexdigest() if response.content else None,
        "body_size": len(response.content or b""),
    }


def _conclusion(response: httpx.Response) -> str:
    if response.status_code in {401, 403}:
        return "reachable_access_controlled"
    if 200 <= response.status_code < 400:
        return "reachable"
    if response.status_code == 404:
        return "not_found"
    return "reachable_with_error_status"


def create_validation_run(
    db: Session,
    vulnerability: VulnerabilityCandidate,
    target: AuthorizedTarget,
    method: str,
    path: str | None,
    requested_by: str | None,
) -> ValidationRun:
    method = method.upper()
    if method not in SAFE_METHODS:
        raise ValidationPolicyError("validation method must be GET, HEAD, or OPTIONS")
    requested_path = normalize_path(path or vulnerability.event.path or "/")
    run = ValidationRun(
        vulnerability_id=vulnerability.id,
        target_id=target.id,
        status="queued",
        requested_by=requested_by,
        request_options={"method": method, "path": requested_path},
    )
    db.add(run)
    db.flush()
    execute_validation_run(db, run, vulnerability, target)
    db.refresh(run)
    return run


def execute_validation_run(
    db: Session,
    run: ValidationRun,
    vulnerability: VulnerabilityCandidate,
    target: AuthorizedTarget,
) -> None:
    method = run.request_options.get("method", "HEAD").upper()
    path = normalize_path(run.request_options.get("path"))
    url = _url(target, path)
    started = time.monotonic()
    run.status = "running"
    run.started_at = _now()

    request_summary = {
        "method": method,
        "target_id": target.id,
        "scheme": target.scheme,
        "host": target.host,
        "port": target.port or default_port(target.scheme),
        "path": path,
        "path_scope": target.path_scope,
        "original_payload_replayed": False,
    }

    if not target.enabled:
        _finish_blocked(db, run, target, method, url, request_summary, "authorized target is disabled")
        return
    if not target_allows_path(target, path):
        _finish_blocked(db, run, target, method, url, request_summary, "path is outside authorized scope")
        return

    try:
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            response = client.request(method, url, headers={"User-Agent": "Flow-Vul-Hunt-Validator/1.0"})
        latency_ms = round((time.monotonic() - started) * 1000)
        conclusion = _conclusion(response)
        result = ValidationResult(
            run_id=run.id,
            target_id=target.id,
            method=method,
            url=url,
            status="completed",
            conclusion=conclusion,
            request_summary=request_summary,
            response_summary=_response_summary(response),
            latency_ms=latency_ms,
        )
        run.status = "completed"
        vulnerability.validation_summary = {
            "last_run_id": run.id,
            "target_id": target.id,
            "status": result.status,
            "conclusion": conclusion,
            "status_code": response.status_code,
            "validated_at": _now().isoformat(),
        }
        if vulnerability.status in {"candidate", "needs_review"} and conclusion.startswith("reachable"):
            vulnerability.status = "validated"
        db.add(result)
    except httpx.TimeoutException as exc:
        _finish_error(db, run, vulnerability, target, method, url, request_summary, "timeout", str(exc))
    except httpx.HTTPError as exc:
        _finish_error(db, run, vulnerability, target, method, url, request_summary, "request_error", str(exc))
    finally:
        run.completed_at = _now()
        db.commit()


def _finish_blocked(
    db: Session,
    run: ValidationRun,
    target: AuthorizedTarget,
    method: str,
    url: str,
    request_summary: dict,
    error: str,
) -> None:
    run.status = "blocked"
    run.error_message = error
    run.completed_at = _now()
    db.add(
        ValidationResult(
            run_id=run.id,
            target_id=target.id,
            method=method,
            url=url,
            status="blocked",
            conclusion="unauthorized_scope",
            request_summary=request_summary,
            response_summary={},
            error_message=error,
        )
    )
    db.commit()


def _finish_error(
    db: Session,
    run: ValidationRun,
    vulnerability: VulnerabilityCandidate,
    target: AuthorizedTarget,
    method: str,
    url: str,
    request_summary: dict,
    conclusion: str,
    error: str,
) -> None:
    run.status = "failed"
    run.error_message = error[:2000]
    vulnerability.validation_summary = {
        "last_run_id": run.id,
        "target_id": target.id,
        "status": "failed",
        "conclusion": conclusion,
        "error": error[:500],
        "validated_at": _now().isoformat(),
    }
    db.add(
        ValidationResult(
            run_id=run.id,
            target_id=target.id,
            method=method,
            url=url,
            status="failed",
            conclusion=conclusion,
            request_summary=request_summary,
            response_summary={},
            error_message=error[:2000],
        )
    )

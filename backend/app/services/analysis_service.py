from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..detection.rules import run_custom_rules, run_rules
from ..ingestion.payload_parser import ParsedPayload
from ..llm.gateway import LLMGateway, LLMResponseError, LLMUnavailableError
from ..llm.prompts import ANALYST_SYSTEM_PROMPT, VERIFIER_SYSTEM_PROMPT
from ..llm.schemas import PayloadAnalysisResult, VerificationResult
from ..models import AnalysisJob, CustomRule, Dataset, DetectionFinding, LLMAnalysis, PayloadEvent
from ..risk.scoring import calculate_risk
from .incident_service import rebuild_incidents
from .vulnerability_service import ensure_event_vulnerability_analysis


PROMPT_VERSION = "1.0"


def _as_parsed(event: PayloadEvent) -> ParsedPayload:
    return ParsedPayload(
        raw_payload=event.raw_payload,
        decoded_payload=event.decoded_payload,
        payload_hash=event.payload_hash,
        protocol=event.protocol,
        http_method=event.http_method,
        host=event.host,
        path=event.path,
        query=event.query,
        headers=event.headers or {},
        body=event.body,
        content_type=event.content_type,
        payload_length=event.payload_length,
        entropy=event.entropy,
        printable_ratio=event.printable_ratio,
        encoded_segment_count=event.encoded_segment_count,
        is_binary=event.is_binary,
        parse_status=event.parse_status,
        parse_error=event.parse_error,
    )


def _event_context(event: PayloadEvent, rule_findings: list[dict]) -> dict:
    decoded = event.decoded_payload
    if event.is_binary and len(decoded) > 4000:
        decoded = decoded[:4000] + "\n[BINARY PAYLOAD TRUNCATED]"
    safe_headers = {
        key: ("[REDACTED]" if key.lower() in {"authorization", "proxy-authorization", "cookie", "set-cookie"} else value)
        for key, value in (event.headers or {}).items()
    }
    return {
        "event": {
            "protocol": event.protocol,
            "method": event.http_method,
            "host": event.host,
            "path": event.path,
            "query": event.query,
            "headers": safe_headers,
            "body": event.body,
            "decoded_payload": decoded,
            "is_binary": event.is_binary,
            "entropy": event.entropy,
            "parse_status": event.parse_status,
        },
        "deterministic_findings": rule_findings,
    }


def _save_llm_success(db: Session, event: PayloadEvent, agent: str, gateway_result) -> LLMAnalysis:
    record = LLMAnalysis(
        event_id=event.id,
        agent_name=agent,
        provider=gateway_result.provider_name,
        model_name=gateway_result.model_name,
        prompt_version=PROMPT_VERSION,
        request_hash=gateway_result.request_hash,
        structured_result=gateway_result.data.model_dump(),
        token_usage=gateway_result.token_usage,
        latency_ms=gateway_result.latency_ms,
        status="completed",
    )
    db.add(record)
    return record


def _save_llm_failure(db: Session, event: PayloadEvent, agent: str, exc: Exception) -> None:
    request_hash = hashlib.sha256(f"{event.payload_hash}:{agent}:{PROMPT_VERSION}".encode()).hexdigest()
    db.add(
        LLMAnalysis(
            event_id=event.id,
            agent_name=agent,
            provider="provider-router",
            model_name=",".join(get_settings().route_for(agent))[:128],
            prompt_version=PROMPT_VERSION,
            request_hash=request_hash,
            status="unavailable" if isinstance(exc, LLMUnavailableError) else "failed",
            error_message=str(exc)[:2000],
        )
    )


def _evidence_supported(event: PayloadEvent, fragment: str) -> bool:
    if not fragment:
        return False
    return fragment in event.decoded_payload or fragment in event.raw_payload


def _should_call_llm(event: PayloadEvent, rule_count: int, scope: str) -> bool:
    if scope == "all":
        return not event.is_binary or rule_count > 0
    return rule_count > 0 or event.parse_status != "success" or (not event.is_binary and event.entropy >= 6.2)


def analyze_event(db: Session, event: PayloadEvent, use_llm: bool, llm_scope: str, force: bool) -> None:
    if force:
        db.execute(delete(DetectionFinding).where(DetectionFinding.event_id == event.id))
        db.execute(delete(LLMAnalysis).where(LLMAnalysis.event_id == event.id))
    elif event.findings or event.llm_analyses:
        ensure_event_vulnerability_analysis(db, event, force=False)
        return

    parsed = _as_parsed(event)
    custom_rules = list(db.scalars(select(CustomRule).where(CustomRule.enabled.is_(True))).all())
    matches = [*run_rules(parsed), *run_custom_rules(parsed, custom_rules)]
    finding_dicts: list[dict] = []
    for match in matches:
        finding = DetectionFinding(
            event_id=event.id,
            detector_type=match.detector_type,
            detector_name=match.detector_name,
            attack_type=match.attack_type,
            severity=match.severity,
            confidence=match.confidence,
            matched_fragment=match.matched_fragment,
            evidence=match.evidence,
        )
        db.add(finding)
        finding_dicts.append(
            {
                "detector_type": finding.detector_type,
                "detector_name": finding.detector_name,
                "attack_type": finding.attack_type,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "matched_fragment": finding.matched_fragment,
            }
        )

    if use_llm and _should_call_llm(event, len(matches), llm_scope):
        gateway = LLMGateway()
        context = _event_context(event, finding_dicts)
        try:
            analyst_call = gateway.complete_json(
                ANALYST_SYSTEM_PROMPT,
                context,
                PayloadAnalysisResult,
                agent_name="payload_analyst",
            )
            analyst = analyst_call.data
            _save_llm_success(db, event, "payload_analyst", analyst_call)
            supported_indexes = [
                index for index, evidence in enumerate(analyst.evidence)
                if _evidence_supported(event, evidence.fragment)
            ]
            verification_payload = {
                "event": context["event"],
                "analyst_result": analyst.model_dump(),
                "server_supported_evidence_indexes": supported_indexes,
            }
        except (LLMUnavailableError, LLMResponseError) as exc:
            _save_llm_failure(db, event, "payload_analyst", exc)
        else:
            try:
                verifier_call = gateway.complete_json(
                    VERIFIER_SYSTEM_PROMPT,
                    verification_payload,
                    VerificationResult,
                    agent_name="evidence_verifier",
                )
                verifier = verifier_call.data
                _save_llm_success(db, event, "evidence_verifier", verifier_call)
                valid_indexes = set(supported_indexes) & set(verifier.supported_evidence_indexes)
                if (
                    verifier.accepted
                    and verifier.corrected_verdict in {"malicious", "suspicious"}
                    and valid_indexes
                ):
                    confidence = min(analyst.confidence, verifier.corrected_confidence)
                    severity = "critical" if confidence >= 0.9 else "high" if confidence >= 0.75 else "medium"
                    attack_types = analyst.attack_types or ["unknown"]
                    fragments = [analyst.evidence[index].fragment for index in sorted(valid_indexes)]
                    for attack_type in attack_types:
                        finding = DetectionFinding(
                            event_id=event.id,
                            detector_type="llm_verified",
                            detector_name="payload-analyst+evidence-verifier",
                            attack_type=attack_type,
                            severity=severity,
                            confidence=confidence,
                            matched_fragment=" | ".join(fragments)[:1000],
                            evidence={
                                "intent": analyst.intent,
                                "target_component": analyst.target_component,
                                "verifier_explanation": verifier.explanation,
                            },
                        )
                        db.add(finding)
                        finding_dicts.append(
                            {
                                "detector_type": finding.detector_type,
                                "attack_type": finding.attack_type,
                                "severity": finding.severity,
                                "confidence": finding.confidence,
                            }
                        )
            except (LLMUnavailableError, LLMResponseError) as exc:
                _save_llm_failure(db, event, "evidence_verifier", exc)

    score, verdict, explanation = calculate_risk(finding_dicts, event.parse_status, event.is_binary)
    event.risk_score = score
    event.verdict = verdict
    # Keep the deterministic risk explanation as an auditable finding without affecting the score.
    if finding_dicts:
        db.add(
            DetectionFinding(
                event_id=event.id,
                detector_type="risk",
                detector_name="explainable-risk-v1",
                attack_type="risk_assessment",
                severity="info",
                confidence=1.0,
                evidence=explanation,
            )
        )
    db.flush()
    ensure_event_vulnerability_analysis(db, event, force=force)


def run_analysis_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)
        if not job:
            return
        dataset = db.get(Dataset, job.dataset_id)
        if not dataset:
            job.status = "failed"
            job.error_message = "dataset not found"
            db.commit()
            return
        if job.cancel_requested:
            job.status = "canceled"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        dataset.status = "analyzing"
        events = db.scalars(
            select(PayloadEvent).where(PayloadEvent.dataset_id == dataset.id).order_by(PayloadEvent.row_number)
        ).all()
        job.total = len(events)
        db.commit()

        canceled = False
        for event in events:
            db.refresh(job)
            if job.cancel_requested:
                canceled = True
                break
            try:
                analyze_event(db, event, job.use_llm, job.llm_scope, job.force)
                job.succeeded += 1
            except Exception as exc:  # One malformed event must not abort the dataset.
                db.rollback()
                job = db.get(AnalysisJob, job_id)
                job.failed += 1
                job.error_message = f"last event error: {type(exc).__name__}: {exc}"[:2000]
            job.processed += 1
            db.commit()

        dataset = db.get(Dataset, job.dataset_id)
        dataset.analyzed_count = job.succeeded
        if canceled:
            dataset.status = "analysis_canceled"
            job.status = "canceled"
        else:
            dataset.status = "completed" if job.failed == 0 else "completed_with_errors"
            job.status = "completed" if job.failed == 0 else "completed_with_errors"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        rebuild_incidents(db, dataset.id)
    except Exception as exc:
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()

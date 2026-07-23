from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..llm.gateway import LLMGateway, LLMResponseError, LLMUnavailableError
from ..llm.prompts import REPORT_SYSTEM_PROMPT
from ..llm.schemas import IncidentReportContent
from ..models import (
    DetectionFinding,
    Incident,
    IncidentReport,
    PayloadEvent,
    ValidationResult,
    ValidationRun,
    VulnerabilityCandidate,
)


def _report_facts(db: Session, incident: Incident) -> tuple[list[dict], set[str], set[str], list[dict], list[dict]]:
    facts: list[dict] = []
    event_ids: set[str] = set()
    attack_types: set[str] = set()
    vulnerability_facts: list[dict] = []
    validation_facts: list[dict] = []
    for link in sorted(incident.event_links, key=lambda item: item.sort_order):
        event = db.get(PayloadEvent, link.event_id)
        if not event:
            continue
        findings = db.scalars(
            select(DetectionFinding).where(
                DetectionFinding.event_id == event.id,
                DetectionFinding.detector_type != "risk",
            )
        ).all()
        finding_facts = []
        for finding in findings:
            attack_types.add(finding.attack_type)
            finding_facts.append({
                "attack_type": finding.attack_type,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "matched_fragment": finding.matched_fragment,
            })
        vulnerabilities = db.scalars(
            select(VulnerabilityCandidate).where(VulnerabilityCandidate.event_id == event.id)
        ).all()
        event_vulnerability_facts = []
        for vulnerability in vulnerabilities:
            item = {
                "id": vulnerability.id,
                "event_id": event.id,
                "candidate_type": vulnerability.candidate_type,
                "severity": vulnerability.severity,
                "confidence": vulnerability.confidence,
                "status": vulnerability.status,
                "target_component": vulnerability.target_component,
                "validation_summary": vulnerability.validation_summary,
            }
            event_vulnerability_facts.append(item)
            vulnerability_facts.append(item)
        event_ids.add(event.id)
        facts.append({
            "event_id": event.id,
            "row_number": event.row_number,
            "host": event.host,
            "method": event.http_method,
            "path": event.path,
            "risk_score": event.risk_score,
            "verdict": event.verdict,
            "findings": finding_facts,
            "vulnerability_candidates": event_vulnerability_facts,
        })
    if vulnerability_facts:
        vuln_ids = [item["id"] for item in vulnerability_facts]
        type_by_id = {item["id"]: item["candidate_type"] for item in vulnerability_facts}
        validation_facts = [
            {
                "vulnerability_id": run.vulnerability_id,
                "candidate_type": type_by_id.get(run.vulnerability_id),
                "status": result.status,
                "conclusion": result.conclusion,
                "method": result.method,
                "url": result.url,
                "latency_ms": result.latency_ms,
                "response_summary": result.response_summary,
            }
            for result, run in db.execute(
                select(ValidationResult, ValidationRun)
                .join(ValidationRun, ValidationRun.id == ValidationResult.run_id)
                .where(ValidationRun.vulnerability_id.in_(vuln_ids))
            ).all()
        ][:50]
    return facts, event_ids, attack_types, vulnerability_facts[:50], validation_facts


def _deterministic_content(
    incident: Incident,
    facts: list[dict],
    attack_types: set[str],
    vulnerability_facts: list[dict],
    validation_facts: list[dict],
) -> IncidentReportContent:
    return IncidentReportContent(
        executive_summary=(
            f"数据集中发现一个包含 {len(facts)} 条实际 Payload 的活动簇，"
            f"聚类类型为 {incident.incident_type}，风险分为 {incident.risk_score}。"
        ),
        technical_summary=incident.summary,
        evidence_event_ids=[fact["event_id"] for fact in facts],
        attack_types=sorted(attack_types),
        vulnerability_candidates=vulnerability_facts,
        validation_results=validation_facts,
        recommended_actions=[
            "人工复核列出的原始 Payload 与检测证据。",
            "将漏洞候选区分为候选、已验证线索和人工确认漏洞，避免把可达性误当成利用成功。",
            "结合真实源/目的 IP、时间戳、会话和资产日志进一步确认影响范围。",
        ],
        limitations=[
            "当前数据仅包含 Payload，缺少时间、源/目的地址、会话和资产上下文。",
            "活动簇表示 Payload 相关性，不证明来自同一攻击者或已成功利用。",
        ],
    )


def generate_report(db: Session, incident_id: str, use_llm: bool) -> IncidentReport:
    incident = db.scalar(
        select(Incident).where(Incident.id == incident_id).options(selectinload(Incident.event_links))
    )
    if not incident:
        raise LookupError("incident not found")
    facts, event_ids, attack_types, vulnerability_facts, validation_facts = _report_facts(db, incident)
    fallback = _deterministic_content(incident, facts, attack_types, vulnerability_facts, validation_facts)
    content = fallback
    generator = "deterministic"
    model_name = None
    status = "completed"
    error_message = None

    if use_llm:
        try:
            call = LLMGateway().complete_json(
                REPORT_SYSTEM_PROMPT,
                {
                    "incident": {
                        "id": incident.id,
                        "type": incident.incident_type,
                        "risk_score": incident.risk_score,
                        "severity": incident.severity,
                    },
                    "event_facts": facts,
                    "vulnerability_candidates": vulnerability_facts,
                    "validation_results": validation_facts,
                },
                IncidentReportContent,
                agent_name="report_generator",
            )
            candidate = call.data
            if not set(candidate.evidence_event_ids).issubset(event_ids):
                raise LLMResponseError("report cited event IDs outside the incident")
            content = candidate
            generator = "llm_verified_sources"
            model_name = f"{call.provider_name}:{call.model_name}"
        except (LLMUnavailableError, LLMResponseError) as exc:
            status = "completed_with_fallback"
            error_message = str(exc)[:2000]

    report = IncidentReport(
        incident_id=incident.id,
        generator=generator,
        model_name=model_name,
        content=content.model_dump(),
        status=status,
        error_message=error_message,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report

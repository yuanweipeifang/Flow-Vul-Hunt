from __future__ import annotations

import re
from typing import Any

import httpx
from sqlalchemy.orm.attributes import flag_modified

from ..llm.gateway import LLMGateway
from ..llm.prompts import CVE_QUERY_PLAN_SYSTEM_PROMPT, CVE_RESEARCH_SYNTHESIS_SYSTEM_PROMPT
from ..llm.schemas import CVEResearchQueryPlan, CVEResearchResult
from ..models import VulnerabilityCandidate, utcnow


CVE_ID_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)
NVD_CVE_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


class CVESearchError(RuntimeError):
    pass


def _event_payload(vulnerability: VulnerabilityCandidate) -> dict[str, Any]:
    event = vulnerability.event
    if not event:
        return {}
    return {
        "id": event.id,
        "row_number": event.row_number,
        "protocol": event.protocol,
        "http_method": event.http_method,
        "host": event.host,
        "path": event.path,
        "query": event.query,
        "content_type": event.content_type,
        "decoded_payload": (event.decoded_payload or "")[:4000],
        "risk_score": event.risk_score,
        "verdict": event.verdict,
        "findings": [
            {
                "detector_type": finding.detector_type,
                "detector_name": finding.detector_name,
                "attack_type": finding.attack_type,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "matched_fragment": finding.matched_fragment,
                "evidence": finding.evidence,
            }
            for finding in event.findings[:12]
        ],
    }


def build_cve_research_payload(vulnerability: VulnerabilityCandidate) -> dict[str, Any]:
    return {
        "candidate": {
            "id": vulnerability.id,
            "candidate_type": vulnerability.candidate_type,
            "title": vulnerability.title,
            "target_component": vulnerability.target_component,
            "severity": vulnerability.severity,
            "confidence": vulnerability.confidence,
            "status": vulnerability.status,
            "impact": vulnerability.impact,
            "evidence": vulnerability.evidence or {},
            "validation_summary": vulnerability.validation_summary or {},
        },
        "related_event": _event_payload(vulnerability),
        "output_contract": {
            "scope": "Use live NVD search results plus supplied evidence.",
            "empty_result": "Return empty candidates if no retrieved CVE is supported by the supplied features.",
        },
    }


def _extract_existing_cve_ids(value: Any) -> list[str]:
    try:
        text = value if isinstance(value, str) else str(value)
    except Exception:
        return []
    return list(dict.fromkeys(match.upper() for match in CVE_ID_RE.findall(text)))


def _fallback_queries(payload: dict[str, Any]) -> list[str]:
    candidate = payload["candidate"]
    values = [
        candidate.get("target_component"),
        candidate.get("candidate_type", "").replace("_", " "),
        candidate.get("title"),
    ]
    joined = " ".join(str(value) for value in values if value).strip()
    return [joined[:180]] if joined else [str(candidate.get("candidate_type") or "web vulnerability")]


def _nvd_record(item: dict[str, Any]) -> dict[str, Any]:
    cve = item.get("cve") or {}
    metrics = cve.get("metrics") or {}
    descriptions = cve.get("descriptions") or []
    english_description = next(
        (description.get("value") for description in descriptions if description.get("lang") == "en"),
        descriptions[0].get("value") if descriptions else "",
    )
    weaknesses = cve.get("weaknesses") or []
    cwes = []
    for weakness in weaknesses:
        for description in weakness.get("description") or []:
            value = description.get("value")
            if value:
                cwes.append(value)
    return {
        "id": cve.get("id"),
        "published": cve.get("published"),
        "last_modified": cve.get("lastModified"),
        "vuln_status": cve.get("vulnStatus"),
        "description": english_description,
        "source_identifier": cve.get("sourceIdentifier"),
        "cvss_v31": (metrics.get("cvssMetricV31") or [{}])[0],
        "cvss_v40": (metrics.get("cvssMetricV40") or [{}])[0],
        "cwes": list(dict.fromkeys(cwes))[:8],
        "references": [
            {
                "url": ref.get("url"),
                "source": ref.get("source"),
                "tags": ref.get("tags") or [],
            }
            for ref in (cve.get("references") or {}).get("referenceData", [])[:8]
        ],
    }


def _fetch_nvd_cves(query_plan: CVEResearchQueryPlan) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    searches: list[dict[str, Any]] = []
    with httpx.Client(timeout=20, headers={"User-Agent": "Flow-Vul-Hunt-CVE-Research/0.1"}) as client:
        for cve_id in query_plan.known_cve_ids[:20]:
            response = client.get(NVD_CVE_API_URL, params={"cveId": cve_id})
            response.raise_for_status()
            payload = response.json()
            items = payload.get("vulnerabilities") or []
            searches.append({"type": "cveId", "query": cve_id, "total_results": payload.get("totalResults", len(items))})
            for item in items:
                record = _nvd_record(item)
                if record.get("id"):
                    records[record["id"]] = record
        for query in query_plan.search_queries[:6]:
            query = query.strip()
            if not query:
                continue
            response = client.get(NVD_CVE_API_URL, params={"keywordSearch": query, "resultsPerPage": 8})
            response.raise_for_status()
            payload = response.json()
            items = payload.get("vulnerabilities") or []
            searches.append({"type": "keywordSearch", "query": query, "total_results": payload.get("totalResults", len(items))})
            for item in items:
                record = _nvd_record(item)
                if record.get("id"):
                    records[record["id"]] = record
    return {
        "searches": searches,
        "records": list(records.values())[:24],
        "source": "nvd_cve_api_2_0",
        "source_url": NVD_CVE_API_URL,
    }


def research_cves_for_vulnerability(vulnerability: VulnerabilityCandidate) -> dict[str, Any]:
    gateway = LLMGateway()
    candidate_payload = build_cve_research_payload(vulnerability)
    query_call = gateway.complete_json(
        CVE_QUERY_PLAN_SYSTEM_PROMPT,
        candidate_payload,
        CVEResearchQueryPlan,
        agent_name="vulnerability_researcher",
    )
    query_plan = query_call.data
    existing_cves = _extract_existing_cve_ids(candidate_payload)
    query_plan = CVEResearchQueryPlan.model_validate(
        {
            "search_queries": query_plan.search_queries or _fallback_queries(candidate_payload),
            "known_cve_ids": list(dict.fromkeys([*query_plan.known_cve_ids, *existing_cves])),
            "rationale": query_plan.rationale,
        }
    )
    try:
        live_results = _fetch_nvd_cves(query_plan)
    except httpx.HTTPError as exc:
        raise CVESearchError(f"NVD CVE search failed: {exc}") from exc
    synthesis_call = gateway.complete_json(
        CVE_RESEARCH_SYNTHESIS_SYSTEM_PROMPT,
        {
            **candidate_payload,
            "query_plan": query_plan.model_dump(),
            "live_cve_search": live_results,
        },
        CVEResearchResult,
        agent_name="vulnerability_researcher",
    )
    result = synthesis_call.data.model_dump()
    return {
        **result,
        "llm_used": True,
        "provider": synthesis_call.provider_name,
        "model": synthesis_call.model_name,
        "request_hash": synthesis_call.request_hash,
        "token_usage": synthesis_call.token_usage,
        "latency_ms": synthesis_call.latency_ms,
        "query_plan": query_plan.model_dump(),
        "query_llm": {
            "provider": query_call.provider_name,
            "model": query_call.model_name,
            "request_hash": query_call.request_hash,
            "latency_ms": query_call.latency_ms,
        },
        "live_cve_search": live_results,
        "researched_at": utcnow().isoformat(),
        "knowledge_scope": "live_nvd_search_plus_llm_synthesis",
    }


def save_cve_research(vulnerability: VulnerabilityCandidate, research: dict[str, Any]) -> None:
    evidence = dict(vulnerability.evidence or {})
    evidence["cve_research"] = research
    vulnerability.evidence = evidence
    flag_modified(vulnerability, "evidence")

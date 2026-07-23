from __future__ import annotations

from collections.abc import Iterable


SEVERITY_VALUE = {"info": 5, "low": 25, "medium": 50, "high": 75, "critical": 95}


def severity_for_score(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    if score >= 20:
        return "low"
    return "info"


def calculate_risk(findings: Iterable[dict], parse_status: str, is_binary: bool) -> tuple[float, str, dict]:
    items = list(findings)
    if not items:
        return 0.0, "unreviewed", {"reason": "no_detection_evidence"}

    strongest = max(items, key=lambda item: SEVERITY_VALUE.get(item["severity"], 0) * item["confidence"])
    severity_component = SEVERITY_VALUE.get(strongest["severity"], 0) * 0.50
    confidence_component = strongest["confidence"] * 100 * 0.30
    detector_types = {item.get("detector_type", "rule") for item in items}
    consistency_component = min(15.0, max(0, len(detector_types) - 1) * 7.5)
    corroboration_component = min(5.0, max(0, len(items) - 1) * 2.5)
    score = severity_component + confidence_component + consistency_component + corroboration_component

    # Parsing uncertainty may lower confidence, but binary data is never considered malicious by itself.
    if parse_status == "failed":
        score *= 0.9
    if is_binary and all(item["attack_type"] == "high_entropy_payload" for item in items):
        score = min(score, 25.0)

    score = round(min(100.0, score), 1)
    verdict = "malicious" if score >= 60 else "suspicious" if score >= 25 else "unreviewed"
    explanation = {
        "strongest_severity": strongest["severity"],
        "strongest_confidence": strongest["confidence"],
        "finding_count": len(items),
        "detector_types": sorted(detector_types),
        "binary_cap_applied": bool(is_binary and score <= 25.0),
    }
    return score, verdict, explanation

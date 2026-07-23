from app.detection.rules import run_rules
from app.ingestion.payload_parser import parse_payload
from app.risk.scoring import calculate_risk


def test_command_injection_has_auditable_fragment() -> None:
    parsed = parse_payload(
        "GET /vuln?callback=shell_exec&cmd=cat/etc/passwd HTTP/1.1\\0D\\0AHost: target.test\\0D\\0A\\0D\\0A"
    )
    matches = run_rules(parsed)
    command = next(match for match in matches if match.attack_type == "command_injection")
    assert command.severity == "critical"
    assert command.matched_fragment in parsed.decoded_payload


def test_high_entropy_binary_alone_is_capped() -> None:
    findings = [{
        "detector_type": "anomaly",
        "attack_type": "high_entropy_payload",
        "severity": "low",
        "confidence": 0.65,
    }]
    score, verdict, _ = calculate_risk(findings, "success", True)
    assert score <= 25
    assert verdict != "malicious"


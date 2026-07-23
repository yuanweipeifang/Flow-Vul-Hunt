from __future__ import annotations

import re
from dataclasses import dataclass

from ..ingestion.payload_parser import ParsedPayload


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    attack_type: str
    severity: str
    confidence: float
    description: str
    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class RuleMatch:
    detector_name: str
    attack_type: str
    severity: str
    confidence: float
    matched_fragment: str
    evidence: dict
    detector_type: str = "rule"


RULES = (
    Rule("WEB-CMD-001", "command_injection", "critical", 0.97, "系统命令执行函数或命令参数", re.compile(r"(?:shell_exec|passthru|system\s*\(|exec\s*\(|cmd=|/bin/(?:sh|bash)|cat(?:%20|\s|/)+(?:/)?etc/passwd)", re.I)),
    Rule("WEB-SQLI-001", "sql_injection", "high", 0.94, "SQL 注入关键结构", re.compile(r"(?:\bunion(?:\s|%20)+select\b|\bselect(?:\s|%20)+.+(?:\s|%20)+from\b|\bsleep\s*\(|\bbenchmark\s*\(|(?:'|%27)(?:\s|%20)*(?:or|and)(?:\s|%20)+['\d])", re.I)),
    Rule("WEB-PATH-001", "path_traversal", "high", 0.95, "路径穿越或敏感文件读取", re.compile(r"(?:(?:\.\./|\.\.\\|%2e%2e(?:%2f|/)){2,}|/(?:etc/passwd|proc/self|windows/win\.ini))", re.I)),
    Rule("WEB-EXPR-001", "expression_injection", "critical", 0.96, "服务端表达式或模板执行", re.compile(r"(?:#\{.{0,800}(?:Runtime|getRuntime|ProcessBuilder|StreamUtils)|\$\{.{0,500}(?:jndi|runtime|exec))", re.I | re.S)),
    Rule("WEB-JNDI-001", "jndi_injection", "critical", 0.99, "JNDI/Log4Shell 风格注入", re.compile(r"\$\{\s*jndi\s*:(?:ldap|rmi|dns|iiop):", re.I)),
    Rule("WEB-WEBSHELL-001", "webshell_activity", "critical", 0.92, "常见 WebShell 操作特征", re.compile(r"(?:eval\s*\(|assert\s*\(|base64_decode\s*\(|antsword|behinder|godzilla)", re.I)),
    Rule("WEB-SENSITIVE-001", "sensitive_endpoint_probe", "medium", 0.82, "敏感管理或配置接口探测", re.compile(r"(?:/actuator(?:/|$)|/\.git(?:/|$)|/\.env(?:\?|$)|phpinfo\.php|/server-status)", re.I)),
    Rule("WEB-SSRF-001", "ssrf", "high", 0.88, "疑似访问本机或云元数据地址", re.compile(r"(?:https?://)?(?:127\.0\.0\.1|localhost|169\.254\.169\.254)(?::\d+)?(?:/|$)", re.I)),
    Rule("WEB-XSS-001", "cross_site_scripting", "high", 0.91, "跨站脚本载荷", re.compile(r"(?:<script\b|javascript\s*:|on(?:error|load|mouseover)\s*=|%3cscript)", re.I)),
)


def run_rules(payload: ParsedPayload) -> list[RuleMatch]:
    searchable = "\n".join(
        part for part in (payload.decoded_payload, payload.path, payload.query, payload.body) if part
    )
    matches: list[RuleMatch] = []
    for rule in RULES:
        match = rule.pattern.search(searchable)
        if not match:
            continue
        fragment = match.group(0)[:500]
        matches.append(
            RuleMatch(
                detector_name=rule.rule_id,
                attack_type=rule.attack_type,
                severity=rule.severity,
                confidence=rule.confidence,
                matched_fragment=fragment,
                evidence={"description": rule.description, "field": "normalized_payload"},
                detector_type="rule",
            )
        )
    if payload.entropy >= 7.4 and payload.payload_length >= 128:
        matches.append(
            RuleMatch(
                detector_name="STAT-ENTROPY-001",
                attack_type="high_entropy_payload",
                severity="low" if payload.is_binary else "medium",
                confidence=0.65,
                matched_fragment="",
                evidence={"entropy": payload.entropy, "is_binary": payload.is_binary},
                detector_type="anomaly",
            )
        )
    return matches


def searchable_text(payload: ParsedPayload) -> str:
    return "\n".join(
        part for part in (payload.decoded_payload, payload.path, payload.query, payload.body) if part
    )


def validate_rule_pattern(pattern: str) -> None:
    try:
        re.compile(pattern, re.I | re.S)
    except re.error as exc:
        raise ValueError(f"invalid regular expression: {exc}") from exc


def run_custom_rules(payload: ParsedPayload, rules: list) -> list[RuleMatch]:
    searchable = searchable_text(payload)
    matches: list[RuleMatch] = []
    for rule in rules:
        pattern = re.compile(rule.pattern, re.I | re.S)
        match = pattern.search(searchable)
        if not match:
            continue
        matches.append(
            RuleMatch(
                detector_name=rule.rule_id,
                attack_type=rule.attack_type,
                severity=rule.severity,
                confidence=rule.confidence,
                matched_fragment=match.group(0)[:500],
                evidence={
                    "description": rule.description,
                    "field": "normalized_payload",
                    "rule_name": rule.name,
                },
                detector_type="custom_rule",
            )
        )
    return matches

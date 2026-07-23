from __future__ import annotations

from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..llm.gateway import LLMGateway, LLMResponseError, LLMUnavailableError
from ..llm.prompts import HUNT_SYSTEM_PROMPT
from ..llm.schemas import HuntFilters
from ..models import DetectionFinding, PayloadEvent


ATTACK_KEYWORDS = {
    "命令注入": "command_injection",
    "command injection": "command_injection",
    "sql注入": "sql_injection",
    "sql 注入": "sql_injection",
    "路径穿越": "path_traversal",
    "目录穿越": "path_traversal",
    "表达式注入": "expression_injection",
    "jndi": "jndi_injection",
    "webshell": "webshell_activity",
    "ssrf": "ssrf",
    "xss": "cross_site_scripting",
}


def deterministic_filters(question: str) -> HuntFilters:
    lowered = question.lower()
    values: dict[str, Any] = {}
    for keyword, attack_type in ATTACK_KEYWORDS.items():
        if keyword in lowered:
            values["attack_type"] = attack_type
            break
    if "严重" in lowered or "critical" in lowered:
        values["min_risk_score"] = 80
    elif "高危" in lowered or "high risk" in lowered:
        values["min_risk_score"] = 60
    if "恶意" in lowered or "malicious" in lowered:
        values["verdict"] = "malicious"
    elif "可疑" in lowered or "suspicious" in lowered:
        values["verdict"] = "suspicious"
    if "二进制" in lowered or "binary" in lowered:
        values["is_binary"] = True
    for method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        if method.lower() in lowered.split():
            values["method"] = method
            break
    return HuntFilters.model_validate(values)


def interpret_hunt(question: str, use_llm: bool) -> tuple[HuntFilters, bool, str | None]:
    fallback = deterministic_filters(question)
    if not use_llm:
        return fallback, False, None
    try:
        result = LLMGateway().complete_json(
            HUNT_SYSTEM_PROMPT,
            {"question": question},
            HuntFilters,
            agent_name="hunt_interpreter",
        )
        return result.data, True, None
    except LLMUnavailableError as exc:
        return fallback, False, str(exc)
    except LLMResponseError as exc:
        return fallback, False, f"LLM filter interpretation failed; deterministic fallback used: {exc}"


def execute_hunt(
    db: Session, filters: HuntFilters, dataset_id: str | None, limit: int
) -> list[PayloadEvent]:
    statement: Select = select(PayloadEvent)
    if filters.attack_type:
        statement = statement.join(DetectionFinding).where(
            DetectionFinding.attack_type == filters.attack_type
        )
    if dataset_id:
        statement = statement.where(PayloadEvent.dataset_id == dataset_id)
    if filters.verdict:
        statement = statement.where(PayloadEvent.verdict == filters.verdict)
    if filters.min_risk_score is not None:
        statement = statement.where(PayloadEvent.risk_score >= filters.min_risk_score)
    if filters.host_contains:
        statement = statement.where(PayloadEvent.host.ilike(f"%{filters.host_contains}%"))
    if filters.path_contains:
        statement = statement.where(PayloadEvent.path.ilike(f"%{filters.path_contains}%"))
    if filters.method:
        statement = statement.where(PayloadEvent.http_method == filters.method.upper())
    if filters.payload_contains:
        needle = f"%{filters.payload_contains}%"
        statement = statement.where(
            or_(PayloadEvent.raw_payload.ilike(needle), PayloadEvent.decoded_payload.ilike(needle))
        )
    if filters.is_binary is not None:
        statement = statement.where(PayloadEvent.is_binary == filters.is_binary)
    return list(
        db.scalars(statement.distinct().order_by(PayloadEvent.risk_score.desc()).limit(limit)).all()
    )

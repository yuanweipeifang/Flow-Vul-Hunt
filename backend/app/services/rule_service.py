from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..detection.rules import run_custom_rules, run_rules, validate_rule_pattern
from ..ingestion.payload_parser import parse_payload
from ..models import CustomRule, PayloadEvent
from ..schemas import CustomRuleCreate, CustomRuleUpdate, RuleDryRunResult, RuleDryRunSample
from .analysis_service import _as_parsed


def create_custom_rule(db: Session, request: CustomRuleCreate) -> CustomRule:
    validate_rule_pattern(request.pattern)
    rule = CustomRule(**request.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_custom_rule(db: Session, rule: CustomRule, request: CustomRuleUpdate) -> CustomRule:
    changes = request.model_dump(exclude_unset=True)
    if "pattern" in changes:
        validate_rule_pattern(changes["pattern"])
    for field, value in changes.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


def enabled_custom_rules(db: Session) -> list[CustomRule]:
    return list(db.scalars(select(CustomRule).where(CustomRule.enabled.is_(True))).all())


def test_rules_against_payload(db: Session, payload: str, include_builtin: bool = True) -> tuple[str, bool, list]:
    parsed = parse_payload(payload)
    matches = []
    if include_builtin:
        matches.extend(run_rules(parsed))
    matches.extend(run_custom_rules(parsed, enabled_custom_rules(db)))
    return parsed.parse_status, parsed.is_binary, matches


def dry_run_custom_rule(
    db: Session,
    request: CustomRuleCreate,
    dataset_id: str | None = None,
    limit: int = 500,
) -> RuleDryRunResult:
    validate_rule_pattern(request.pattern)
    rule = CustomRule(**request.model_dump())
    statement = select(PayloadEvent)
    if dataset_id:
        statement = statement.where(PayloadEvent.dataset_id == dataset_id)
    events = list(db.scalars(statement.order_by(PayloadEvent.created_at.desc()).limit(limit)).all())
    samples: list[RuleDryRunSample] = []
    matched = 0
    for event in events:
        matches = run_custom_rules(_as_parsed(event), [rule])
        if not matches:
            continue
        matched += 1
        if len(samples) < 20:
            samples.append(
                RuleDryRunSample(
                    event_id=event.id,
                    dataset_id=event.dataset_id,
                    row_number=event.row_number,
                    host=event.host,
                    path=event.path,
                    matched_fragment=matches[0].matched_fragment,
                )
            )
    tested = len(events)
    return RuleDryRunResult(
        tested=tested,
        matched=matched,
        match_rate=round(matched / tested, 4) if tested else 0.0,
        samples=samples,
    )

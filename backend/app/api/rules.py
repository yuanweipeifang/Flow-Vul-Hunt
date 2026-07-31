from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit_log
from ..detection.rules import RULES
from ..database import get_db
from ..models import CustomRule
from ..schemas import (
    CustomRuleCreate,
    CustomRuleOut,
    CustomRuleUpdate,
    RuleMatchOut,
    RuleDryRunRequest,
    RuleDryRunResult,
    RuleOut,
    RuleTestRequest,
    RuleTestResult,
)
from ..services.rule_service import create_custom_rule, dry_run_custom_rule, test_rules_against_payload, update_custom_rule
from ..security import Actor, get_actor, require_roles

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), _actor: Actor = Depends(get_actor)) -> list[RuleOut]:
    items = [
        RuleOut(
            rule_id=rule.rule_id,
            attack_type=rule.attack_type,
            severity=rule.severity,
            confidence=rule.confidence,
            description=rule.description,
            detector_type="rule",
            enabled=True,
        )
        for rule in RULES
    ]
    items.append(
        RuleOut(
            rule_id="STAT-ENTROPY-001",
            attack_type="high_entropy_payload",
            severity="medium",
            confidence=0.65,
            description="高熵 Payload 统计异常",
            detector_type="anomaly",
            enabled=True,
        )
    )
    custom_rules = db.scalars(select(CustomRule).order_by(CustomRule.created_at.desc())).all()
    for rule in custom_rules:
        items.append(
            RuleOut(
                rule_id=rule.rule_id,
                attack_type=rule.attack_type,
                severity=rule.severity,
                confidence=rule.confidence,
                description=rule.description,
                detector_type="custom_rule",
                enabled=rule.enabled,
            )
        )
    return items


@router.get("/custom", response_model=list[CustomRuleOut])
def list_custom_rules(db: Session = Depends(get_db), _actor: Actor = Depends(get_actor)) -> list[CustomRule]:
    return list(db.scalars(select(CustomRule).order_by(CustomRule.created_at.desc())).all())


@router.post("/custom", response_model=CustomRuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(
    request: CustomRuleCreate,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> CustomRule:
    try:
        rule = create_custom_rule(db, request)
        audit_log(db, "rule.create", "custom_rule", rule.rule_id)
        db.commit()
        db.refresh(rule)
        return rule
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="rule_id already exists") from exc


@router.patch("/custom/{rule_id}", response_model=CustomRuleOut)
def update_rule(
    rule_id: str,
    request: CustomRuleUpdate,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> CustomRule:
    rule = db.scalar(select(CustomRule).where(CustomRule.rule_id == rule_id))
    if not rule:
        raise HTTPException(status_code=404, detail="custom rule not found")
    try:
        rule = update_custom_rule(db, rule, request)
        audit_log(db, "rule.update", "custom_rule", rule.rule_id, request.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(rule)
        return rule
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/custom/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> None:
    rule = db.scalar(select(CustomRule).where(CustomRule.rule_id == rule_id))
    if not rule:
        raise HTTPException(status_code=404, detail="custom rule not found")
    db.delete(rule)
    audit_log(db, "rule.delete", "custom_rule", rule_id)
    db.commit()


@router.post("/test", response_model=RuleTestResult)
def test_rules(
    request: RuleTestRequest,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> RuleTestResult:
    parse_status, is_binary, matches = test_rules_against_payload(db, request.payload)
    return RuleTestResult(
        parse_status=parse_status,
        is_binary=is_binary,
        matches=[
            RuleMatchOut(
                detector_name=match.detector_name,
                detector_type=match.detector_type,
                attack_type=match.attack_type,
                severity=match.severity,
                confidence=match.confidence,
                matched_fragment=match.matched_fragment,
                evidence=match.evidence,
            )
            for match in matches
        ],
    )


@router.post("/dry-run", response_model=RuleDryRunResult)
def dry_run_rule(
    request: RuleDryRunRequest,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> RuleDryRunResult:
    try:
        result = dry_run_custom_rule(db, request.rule, request.dataset_id, request.limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_log(
        db,
        "rule.dry_run",
        "custom_rule",
        request.rule.rule_id,
        {"dataset_id": request.dataset_id, "tested": result.tested, "matched": result.matched},
    )
    db.commit()
    return result

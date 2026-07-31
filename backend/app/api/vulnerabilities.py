from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..audit import audit_log
from ..database import get_db
from ..models import AuthorizedTarget, PayloadEvent, ValidationRun, VulnerabilityCandidate
from ..schemas import (
    ValidationRunOut,
    VulnerabilityAnalysisOut,
    VulnerabilityCandidateOut,
    VulnerabilityGroupOut,
    VulnerabilityCandidateUpdate,
    VulnerabilityValidateRequest,
)
from ..services.validation_service import ValidationPolicyError, create_validation_run
from ..security import Actor, get_actor, require_roles
from ..services.event_mapper import event_summary

router = APIRouter(prefix="/vulnerabilities", tags=["vulnerabilities"])


SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _confidence_factors(vulnerability: VulnerabilityCandidate) -> list[str]:
    evidence = vulnerability.evidence or {}
    if evidence.get("confidence_factors"):
        return evidence["confidence_factors"]
    factors = []
    if evidence.get("rule_findings"):
        factors.append(f"命中 {len(evidence['rule_findings'])} 条检测规则")
    if evidence.get("signals"):
        factors.append(f"提取到 {len(evidence['signals'])} 个漏洞相关信号")
    feature_refs = evidence.get("feature_refs") or {}
    populated_refs = [name for name, value in feature_refs.items() if value]
    if populated_refs:
        factors.append("关联特征：" + ", ".join(populated_refs))
    if vulnerability.confidence >= 0.75:
        factors.append("综合置信度达到高优先级研判阈值")
    else:
        factors.append("综合置信度仍需人工上下文补强")
    return factors


def _false_positive_risks(vulnerability: VulnerabilityCandidate) -> list[str]:
    evidence = vulnerability.evidence or {}
    risks = list(evidence.get("false_positive_risks") or [])
    risks.extend(evidence.get("missing_context") or [])
    if not vulnerability.validation_summary:
        risks.append("尚未进行主动验证，当前只能作为漏洞候选处理。")
    type_risks = {
        "cross_site_scripting": "仅凭请求 Payload 无法确认响应是否反射或是否存在输出编码。",
        "sensitive_endpoint_exposure": "敏感路径探测不等于真实可访问，需要结合状态码、认证和响应摘要确认。",
        "webshell_activity": "WebShell 关键字可能来自扫描器或蜜罐流量，需要结合服务器侧证据确认。",
        "file_upload_risk": "multipart 或 filename 信号只能证明存在上传形态，不能证明文件可执行或可访问。",
    }
    if vulnerability.candidate_type in type_risks:
        risks.append(type_risks[vulnerability.candidate_type])
    return list(dict.fromkeys(risks))[:6]


def _analysis_summary(vulnerability: VulnerabilityCandidate) -> str:
    evidence = vulnerability.evidence or {}
    if evidence.get("analysis_summary"):
        return evidence["analysis_summary"]
    return (
        f"{vulnerability.title}，当前状态为 {vulnerability.status}，"
        f"置信度 {vulnerability.confidence:.2f}，影响判断：{vulnerability.impact}"
    )


@router.get("", response_model=list[VulnerabilityCandidateOut])
def list_vulnerabilities(
    dataset_id: str | None = None,
    candidate_type: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> list[VulnerabilityCandidate]:
    statement = select(VulnerabilityCandidate)
    if dataset_id:
        statement = statement.where(VulnerabilityCandidate.dataset_id == dataset_id)
    if candidate_type:
        statement = statement.where(VulnerabilityCandidate.candidate_type == candidate_type)
    if status:
        statement = statement.where(VulnerabilityCandidate.status == status)
    if severity:
        statement = statement.where(VulnerabilityCandidate.severity == severity)
    if min_confidence is not None:
        statement = statement.where(VulnerabilityCandidate.confidence >= min_confidence)
    return list(
        db.scalars(
            statement.order_by(VulnerabilityCandidate.confidence.desc(), VulnerabilityCandidate.created_at.desc())
            .limit(limit)
        ).all()
    )


@router.get("/groups", response_model=list[VulnerabilityGroupOut])
def group_vulnerabilities(
    dataset_id: str | None = None,
    candidate_type: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> list[VulnerabilityGroupOut]:
    statement = select(VulnerabilityCandidate)
    if dataset_id:
        statement = statement.where(VulnerabilityCandidate.dataset_id == dataset_id)
    if candidate_type:
        statement = statement.where(VulnerabilityCandidate.candidate_type == candidate_type)
    if status:
        statement = statement.where(VulnerabilityCandidate.status == status)
    rows = db.scalars(statement.order_by(VulnerabilityCandidate.confidence.desc()).limit(5000)).all()
    groups: dict[str, dict] = {}
    for item in rows:
        key = f"{item.dataset_id}:{item.candidate_type}:{item.target_component or ''}"
        group = groups.setdefault(
            key,
            {
                "group_key": key,
                "dataset_id": item.dataset_id,
                "candidate_type": item.candidate_type,
                "target_component": item.target_component,
                "count": 0,
                "max_confidence": 0.0,
                "max_severity": item.severity,
                "statuses": {},
                "sample_ids": [],
            },
        )
        group["count"] += 1
        group["max_confidence"] = max(group["max_confidence"], item.confidence)
        if SEVERITY_RANK.get(item.severity, 0) > SEVERITY_RANK.get(group["max_severity"], 0):
            group["max_severity"] = item.severity
        group["statuses"][item.status] = group["statuses"].get(item.status, 0) + 1
        if len(group["sample_ids"]) < 10:
            group["sample_ids"].append(item.id)
    sorted_groups = sorted(groups.values(), key=lambda item: (item["max_confidence"], item["count"]), reverse=True)
    return [VulnerabilityGroupOut(**item) for item in sorted_groups[:limit]]


@router.get("/{vulnerability_id}", response_model=VulnerabilityCandidateOut)
def get_vulnerability(
    vulnerability_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> VulnerabilityCandidate:
    vulnerability = db.get(VulnerabilityCandidate, vulnerability_id)
    if not vulnerability:
        raise HTTPException(status_code=404, detail="vulnerability candidate not found")
    return vulnerability


@router.get("/{vulnerability_id}/analysis", response_model=VulnerabilityAnalysisOut)
def analyze_vulnerability(
    vulnerability_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> VulnerabilityAnalysisOut:
    vulnerability = db.scalar(
        select(VulnerabilityCandidate)
        .where(VulnerabilityCandidate.id == vulnerability_id)
        .options(
            selectinload(VulnerabilityCandidate.event),
            selectinload(VulnerabilityCandidate.validation_runs).selectinload(ValidationRun.results),
        )
    )
    if not vulnerability:
        raise HTTPException(status_code=404, detail="vulnerability candidate not found")
    validation_focus = (vulnerability.evidence or {}).get("recommended_validation_steps") or []
    return VulnerabilityAnalysisOut(
        vulnerability=vulnerability,
        analysis_summary=_analysis_summary(vulnerability),
        confidence_factors=_confidence_factors(vulnerability),
        false_positive_risks=_false_positive_risks(vulnerability),
        validation_focus=validation_focus,
        related_event=event_summary(vulnerability.event),
        validation_history=vulnerability.validation_runs,
    )


@router.patch("/{vulnerability_id}", response_model=VulnerabilityCandidateOut)
def update_vulnerability(
    vulnerability_id: str,
    request: VulnerabilityCandidateUpdate,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> VulnerabilityCandidate:
    vulnerability = db.get(VulnerabilityCandidate, vulnerability_id)
    if not vulnerability:
        raise HTTPException(status_code=404, detail="vulnerability candidate not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(vulnerability, field, value)
    audit_log(db, "vulnerability.update", "vulnerability", vulnerability_id, request.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(vulnerability)
    return vulnerability


@router.post("/{vulnerability_id}/validate", response_model=ValidationRunOut)
def validate_vulnerability(
    vulnerability_id: str,
    request: VulnerabilityValidateRequest,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> ValidationRun:
    vulnerability = db.scalar(
        select(VulnerabilityCandidate)
        .where(VulnerabilityCandidate.id == vulnerability_id)
        .options(selectinload(VulnerabilityCandidate.event))
    )
    if not vulnerability:
        raise HTTPException(status_code=404, detail="vulnerability candidate not found")
    target = db.get(AuthorizedTarget, request.target_id)
    if not target:
        raise HTTPException(status_code=404, detail="authorized target not found")
    try:
        run = create_validation_run(
            db,
            vulnerability,
            target,
            request.method,
            request.path,
            request.requested_by,
        )
    except ValidationPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_log(db, "validation.request", "validation_run", run.id, {"vulnerability_id": vulnerability_id})
    db.commit()
    return db.scalar(
        select(ValidationRun).where(ValidationRun.id == run.id).options(selectinload(ValidationRun.results))
    )

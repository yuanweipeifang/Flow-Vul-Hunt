from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import AuthorizedTarget, ValidationRun, VulnerabilityCandidate
from ..schemas import (
    ValidationRunOut,
    VulnerabilityCandidateOut,
    VulnerabilityCandidateUpdate,
    VulnerabilityValidateRequest,
)
from ..services.validation_service import ValidationPolicyError, create_validation_run

router = APIRouter(prefix="/vulnerabilities", tags=["vulnerabilities"])


@router.get("", response_model=list[VulnerabilityCandidateOut])
def list_vulnerabilities(
    dataset_id: str | None = None,
    candidate_type: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
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


@router.get("/{vulnerability_id}", response_model=VulnerabilityCandidateOut)
def get_vulnerability(vulnerability_id: str, db: Session = Depends(get_db)) -> VulnerabilityCandidate:
    vulnerability = db.get(VulnerabilityCandidate, vulnerability_id)
    if not vulnerability:
        raise HTTPException(status_code=404, detail="vulnerability candidate not found")
    return vulnerability


@router.patch("/{vulnerability_id}", response_model=VulnerabilityCandidateOut)
def update_vulnerability(
    vulnerability_id: str,
    request: VulnerabilityCandidateUpdate,
    db: Session = Depends(get_db),
) -> VulnerabilityCandidate:
    vulnerability = db.get(VulnerabilityCandidate, vulnerability_id)
    if not vulnerability:
        raise HTTPException(status_code=404, detail="vulnerability candidate not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(vulnerability, field, value)
    db.commit()
    db.refresh(vulnerability)
    return vulnerability


@router.post("/{vulnerability_id}/validate", response_model=ValidationRunOut)
def validate_vulnerability(
    vulnerability_id: str,
    request: VulnerabilityValidateRequest,
    db: Session = Depends(get_db),
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
    return db.scalar(
        select(ValidationRun).where(ValidationRun.id == run.id).options(selectinload(ValidationRun.results))
    )

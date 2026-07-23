from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuthorizedTarget, ValidationRun
from ..schemas import AuthorizedTargetCreate, AuthorizedTargetOut, AuthorizedTargetUpdate

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=list[AuthorizedTargetOut])
def list_targets(
    enabled: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AuthorizedTarget]:
    statement = select(AuthorizedTarget)
    if enabled is not None:
        statement = statement.where(AuthorizedTarget.enabled == enabled)
    return list(db.scalars(statement.order_by(AuthorizedTarget.created_at.desc()).limit(limit)).all())


@router.post("", response_model=AuthorizedTargetOut, status_code=status.HTTP_201_CREATED)
def create_target(request: AuthorizedTargetCreate, db: Session = Depends(get_db)) -> AuthorizedTarget:
    target = AuthorizedTarget(**request.model_dump())
    db.add(target)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="authorized target scope already exists") from exc
    db.refresh(target)
    return target


@router.patch("/{target_id}", response_model=AuthorizedTargetOut)
def update_target(
    target_id: str,
    request: AuthorizedTargetUpdate,
    db: Session = Depends(get_db),
) -> AuthorizedTarget:
    target = db.get(AuthorizedTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="authorized target not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="authorized target scope already exists") from exc
    db.refresh(target)
    return target


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(target_id: str, db: Session = Depends(get_db)) -> None:
    target = db.get(AuthorizedTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="authorized target not found")
    run_count = db.scalar(
        select(func.count()).select_from(ValidationRun).where(ValidationRun.target_id == target_id)
    ) or 0
    if run_count:
        raise HTTPException(status_code=409, detail="target has validation audit history; disable it instead")
    db.delete(target)
    db.commit()

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog
from ..schemas import AuditLogOut
from ..security import get_actor

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor=Depends(get_actor),
) -> list[AuditLog]:
    statement = select(AuditLog)
    if action:
        statement = statement.where(AuditLog.action == action)
    if resource_type:
        statement = statement.where(AuditLog.resource_type == resource_type)
    if resource_id:
        statement = statement.where(AuditLog.resource_id == resource_id)
    return list(db.scalars(statement.order_by(AuditLog.created_at.desc()).limit(limit)).all())

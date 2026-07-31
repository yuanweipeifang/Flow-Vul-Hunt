from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditLog
from .request_context import get_actor, get_request_id, get_role


def audit_log(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            action=action,
            actor=get_actor(),
            role=get_role(),
            request_id=get_request_id(),
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
    )

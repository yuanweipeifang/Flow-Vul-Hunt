from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import ValidationRun
from ..schemas import ValidationRunOut
from ..security import Actor, get_actor

router = APIRouter(prefix="/validation-runs", tags=["validation"])


@router.get("/{run_id}", response_model=ValidationRunOut)
def get_validation_run(
    run_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> ValidationRun:
    run = db.scalar(select(ValidationRun).where(ValidationRun.id == run_id).options(selectinload(ValidationRun.results)))
    if not run:
        raise HTTPException(status_code=404, detail="validation run not found")
    return run

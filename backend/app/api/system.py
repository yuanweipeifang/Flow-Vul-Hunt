from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AnalysisJob, Dataset, LLMAnalysis, PayloadEvent, ValidationRun
from ..schemas import SystemMetricsOut
from ..security import get_actor

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/metrics", response_model=SystemMetricsOut)
def system_metrics(db: Session = Depends(get_db), _actor=Depends(get_actor)) -> SystemMetricsOut:
    validation_rows = db.execute(select(ValidationRun.status, func.count()).group_by(ValidationRun.status)).all()
    llm_success = db.scalar(select(func.count()).select_from(LLMAnalysis).where(LLMAnalysis.status == "completed")) or 0
    llm_failure = db.scalar(select(func.count()).select_from(LLMAnalysis).where(LLMAnalysis.status != "completed")) or 0
    return SystemMetricsOut(
        datasets=db.scalar(select(func.count()).select_from(Dataset)) or 0,
        events=db.scalar(select(func.count()).select_from(PayloadEvent)) or 0,
        running_jobs=db.scalar(
            select(func.count()).select_from(AnalysisJob).where(AnalysisJob.status.in_(["queued", "running"]))
        )
        or 0,
        failed_jobs=db.scalar(select(func.count()).select_from(AnalysisJob).where(AnalysisJob.status == "failed")) or 0,
        llm_success=llm_success,
        llm_failure=llm_failure,
        validation_runs_by_status={status: count for status, count in validation_rows},
    )

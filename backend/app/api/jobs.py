from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AnalysisJob, Dataset
from ..schemas import JobOut
from ..services.analysis_service import run_analysis_job

router = APIRouter(prefix="/jobs", tags=["jobs"])
TERMINAL_STATUSES = {"completed", "completed_with_errors", "failed", "canceled"}


@router.get("", response_model=list[JobOut])
def list_jobs(
    dataset_id: str | None = None,
    job_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AnalysisJob]:
    statement = select(AnalysisJob)
    if dataset_id:
        statement = statement.where(AnalysisJob.dataset_id == dataset_id)
    if job_status:
        statement = statement.where(AnalysisJob.status == job_status)
    return list(db.scalars(statement.order_by(AnalysisJob.created_at.desc()).limit(limit)).all())


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail=f"job is already {job.status}")
    job.cancel_requested = True
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/retry", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AnalysisJob:
    source = db.get(AnalysisJob, job_id)
    if not source:
        raise HTTPException(status_code=404, detail="job not found")
    if source.status not in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="only terminal jobs can be retried")
    if not db.get(Dataset, source.dataset_id):
        raise HTTPException(status_code=404, detail="dataset not found")
    active = db.scalar(
        select(AnalysisJob.id).where(
            AnalysisJob.dataset_id == source.dataset_id,
            AnalysisJob.status.in_(["queued", "running"]),
        )
    )
    if active:
        raise HTTPException(status_code=409, detail={"message": "analysis already running", "job_id": active})
    job = AnalysisJob(
        dataset_id=source.dataset_id,
        use_llm=source.use_llm,
        llm_scope=source.llm_scope,
        force=source.force,
        total=source.total,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_analysis_job, job.id)
    return job

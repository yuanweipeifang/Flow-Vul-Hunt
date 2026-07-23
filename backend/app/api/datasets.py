from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..ingestion.csv_reader import DatasetFormatError
from ..models import AnalysisJob, Dataset, DetectionFinding, PayloadEvent
from ..schemas import AnalyzeRequest, DatasetCompareResult, DatasetOut, JobOut
from ..services.analysis_service import run_analysis_job
from ..services.comparison_service import compare_datasets
from ..services.dataset_service import ingest_dataset


router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/upload", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Dataset:
    filename = file.filename or "dataset.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="only CSV files are accepted")
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file exceeds MAX_UPLOAD_BYTES")
    try:
        return ingest_dataset(db, filename, name, content)
    except DatasetFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    dataset_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[Dataset]:
    statement = select(Dataset)
    if dataset_status:
        statement = statement.where(Dataset.status == dataset_status)
    return list(db.scalars(statement.order_by(Dataset.created_at.desc()).limit(limit)).all())


@router.get("/compare", response_model=DatasetCompareResult)
def compare_dataset_pair(
    baseline_dataset_id: str,
    candidate_dataset_id: str,
    db: Session = Depends(get_db),
) -> dict:
    if baseline_dataset_id == candidate_dataset_id:
        raise HTTPException(status_code=422, detail="baseline and candidate datasets must be different")
    if not db.get(Dataset, baseline_dataset_id):
        raise HTTPException(status_code=404, detail="baseline dataset not found")
    if not db.get(Dataset, candidate_dataset_id):
        raise HTTPException(status_code=404, detail="candidate dataset not found")
    return compare_datasets(db, baseline_dataset_id, candidate_dataset_id)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return dataset


@router.get("/{dataset_id}/stats")
def dataset_stats(dataset_id: str, db: Session = Depends(get_db)) -> dict:
    if not db.get(Dataset, dataset_id):
        raise HTTPException(status_code=404, detail="dataset not found")
    verdicts = dict(
        db.execute(
            select(PayloadEvent.verdict, func.count()).where(PayloadEvent.dataset_id == dataset_id).group_by(PayloadEvent.verdict)
        ).all()
    )
    methods = dict(
        db.execute(
            select(PayloadEvent.http_method, func.count())
            .where(PayloadEvent.dataset_id == dataset_id, PayloadEvent.http_method.is_not(None))
            .group_by(PayloadEvent.http_method)
        ).all()
    )
    attack_types = dict(
        db.execute(
            select(DetectionFinding.attack_type, func.count())
            .join(PayloadEvent, PayloadEvent.id == DetectionFinding.event_id)
            .where(PayloadEvent.dataset_id == dataset_id, DetectionFinding.detector_type != "risk")
            .group_by(DetectionFinding.attack_type)
        ).all()
    )
    binary_count = db.scalar(
        select(func.count()).select_from(PayloadEvent).where(
            PayloadEvent.dataset_id == dataset_id, PayloadEvent.is_binary.is_(True)
        )
    )
    return {
        "verdicts": verdicts,
        "http_methods": methods,
        "attack_types": attack_types,
        "binary_count": binary_count or 0,
    }


@router.post("/{dataset_id}/analyze", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def analyze_dataset(
    dataset_id: str,
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AnalysisJob:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    running = db.scalar(
        select(AnalysisJob).where(
            AnalysisJob.dataset_id == dataset_id,
            AnalysisJob.status.in_(["queued", "running"]),
        )
    )
    if running:
        raise HTTPException(status_code=409, detail={"message": "analysis already running", "job_id": running.id})
    job = AnalysisJob(
        dataset_id=dataset_id,
        use_llm=request.use_llm,
        llm_scope=request.llm_scope,
        force=request.force,
        total=dataset.row_count,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_analysis_job, job.id)
    return job


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)) -> None:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    running = db.scalar(
        select(AnalysisJob.id).where(
            AnalysisJob.dataset_id == dataset_id, AnalysisJob.status.in_(["queued", "running"])
        )
    )
    if running:
        raise HTTPException(status_code=409, detail="cannot delete a dataset while analysis is running")
    db.delete(dataset)
    db.commit()


from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..audit import audit_log
from ..database import get_db
from ..ingestion.csv_reader import DatasetFormatError
from ..models import AnalysisJob, Dataset, DetectionFinding, PayloadEvent
from ..schemas import AnalyzeRequest, BatchAnalyzeItem, BatchAnalyzeRequest, BatchAnalyzeResult, DatasetCompareResult, DatasetOut, JobOut, StoredCsvFileOut
from ..services.analysis_service import run_analysis_job
from ..services.comparison_service import compare_datasets
from ..services.dataset_service import csv_storage_root, ensure_dataset_storage_column, ingest_dataset, store_csv_upload
from ..security import Actor, get_actor, require_roles


router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/upload", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> Dataset:
    filename = file.filename or "dataset.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="only CSV files are accepted")
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file exceeds MAX_UPLOAD_BYTES")
    stored_path = store_csv_upload(filename, content)
    try:
        dataset = ingest_dataset(db, stored_path.name, name, content, storage_path=str(stored_path))
        audit_log(db, "dataset.upload", "dataset", dataset.id, {"filename": filename, "storage_path": str(stored_path)})
        db.commit()
        db.refresh(dataset)
        return dataset
    except DatasetFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    dataset_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> list[Dataset]:
    ensure_dataset_storage_column(db)
    statement = select(Dataset)
    if dataset_status:
        statement = statement.where(Dataset.status == dataset_status)
    return list(db.scalars(statement.order_by(Dataset.created_at.desc()).limit(limit)).all())


@router.get("/files", response_model=list[StoredCsvFileOut])
def list_stored_csv_files(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> list[StoredCsvFileOut]:
    ensure_dataset_storage_column(db)
    root = csv_storage_root()
    datasets = db.scalars(select(Dataset)).all()
    by_path = {Path(dataset.storage_path).resolve(): dataset for dataset in datasets if dataset.storage_path}
    by_filename = {dataset.filename: dataset for dataset in datasets}
    files = sorted(root.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)[:limit]
    result: list[StoredCsvFileOut] = []
    for path in files:
        stat = path.stat()
        dataset = by_path.get(path.resolve()) or by_filename.get(path.name)
        result.append(
            StoredCsvFileOut(
                filename=path.name,
                storage_path=str(path),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                dataset_id=dataset.id if dataset else None,
                dataset_name=dataset.name if dataset else None,
                status=dataset.status if dataset else None,
                row_count=dataset.row_count if dataset else None,
                file_sha256=dataset.file_sha256 if dataset else None,
            )
        )
    return result


@router.get("/compare", response_model=DatasetCompareResult)
def compare_dataset_pair(
    baseline_dataset_id: str,
    candidate_dataset_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(get_actor),
) -> dict:
    if baseline_dataset_id == candidate_dataset_id:
        raise HTTPException(status_code=422, detail="baseline and candidate datasets must be different")
    if not db.get(Dataset, baseline_dataset_id):
        raise HTTPException(status_code=404, detail="baseline dataset not found")
    if not db.get(Dataset, candidate_dataset_id):
        raise HTTPException(status_code=404, detail="candidate dataset not found")
    return compare_datasets(db, baseline_dataset_id, candidate_dataset_id)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: str, db: Session = Depends(get_db), _actor: Actor = Depends(get_actor)) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return dataset


@router.get("/{dataset_id}/stats")
def dataset_stats(dataset_id: str, db: Session = Depends(get_db), _actor: Actor = Depends(get_actor)) -> dict:
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
    _actor: Actor = Depends(require_roles("admin", "analyst")),
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
    audit_log(db, "job.start", "dataset", dataset_id, {"job_id": job.id, "force": request.force})
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_analysis_job, job.id)
    return job


@router.post("/analyze-batch", response_model=BatchAnalyzeResult, status_code=status.HTTP_202_ACCEPTED)
def analyze_datasets_batch(
    request: BatchAnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> BatchAnalyzeResult:
    items: list[BatchAnalyzeItem] = []
    queued = 0
    skipped = 0
    for dataset_id in request.dataset_ids:
        dataset = db.get(Dataset, dataset_id)
        if not dataset:
            items.append(BatchAnalyzeItem(dataset_id=dataset_id, status="not_found", message="dataset not found"))
            skipped += 1
            continue
        running = db.scalar(
            select(AnalysisJob).where(
                AnalysisJob.dataset_id == dataset_id,
                AnalysisJob.status.in_(["queued", "running"]),
            )
        )
        if running:
            item_status = "skipped" if request.skip_running else "conflict"
            items.append(
                BatchAnalyzeItem(
                    dataset_id=dataset_id,
                    status=item_status,
                    job=running,
                    message="analysis already running",
                )
            )
            skipped += 1
            continue
        job = AnalysisJob(
            dataset_id=dataset_id,
            use_llm=request.use_llm,
            llm_scope=request.llm_scope,
            force=request.force,
            total=dataset.row_count,
        )
        db.add(job)
        db.flush()
        audit_log(db, "job.start", "dataset", dataset_id, {"job_id": job.id, "force": request.force, "batch": True})
        items.append(BatchAnalyzeItem(dataset_id=dataset_id, status="queued", job=job))
        background_tasks.add_task(run_analysis_job, job.id)
        queued += 1
    db.commit()
    return BatchAnalyzeResult(requested=len(request.dataset_ids), queued=queued, skipped=skipped, items=items)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    _actor: Actor = Depends(require_roles("admin", "analyst")),
) -> None:
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
    audit_log(db, "dataset.delete", "dataset", dataset_id, {"name": dataset.name})
    db.commit()


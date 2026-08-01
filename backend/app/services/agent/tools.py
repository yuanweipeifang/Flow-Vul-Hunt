from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...llm.schemas import HuntFilters
from ...models import (
    AnalysisJob,
    Dataset,
    PayloadEvent,
    ValidationRun,
    VulnerabilityCandidate,
)
from ...services.analysis_service import run_analysis_job
from ...services.dataset_service import csv_storage_root
from ...services.hunt_service import deterministic_filters, execute_hunt
from .constants import HIGH_RISK_TOOLS, RED_TEAM_ATTACK_TYPES, WRITE_REVIEW_TOOLS


def _event_payload(event: PayloadEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "dataset_id": event.dataset_id,
        "row_number": event.row_number,
        "host": event.host,
        "path": event.path,
        "verdict": event.verdict,
        "risk_score": event.risk_score,
        "payload_length": event.payload_length,
        "parse_status": event.parse_status,
    }


def _vulnerability_analysis(vulnerability: VulnerabilityCandidate) -> dict[str, Any]:
    evidence = vulnerability.evidence or {}
    return {
        "id": vulnerability.id,
        "candidate_type": vulnerability.candidate_type,
        "title": vulnerability.title,
        "status": vulnerability.status,
        "severity": vulnerability.severity,
        "confidence": vulnerability.confidence,
        "target_component": vulnerability.target_component,
        "analysis_summary": evidence.get("analysis_summary") or vulnerability.impact,
        "confidence_factors": evidence.get("confidence_factors") or [],
        "false_positive_risks": [
            *list(evidence.get("false_positive_risks") or []),
            *list(evidence.get("missing_context") or []),
        ],
        "validation_focus": evidence.get("recommended_validation_steps") or [],
        "validation_history": [
            {
                "id": run.id,
                "status": run.status,
                "requested_by": run.requested_by,
                "error_message": run.error_message,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }
            for run in vulnerability.validation_runs
        ],
        "related_event": _event_payload(vulnerability.event),
    }


def _attack_surface_map(db: Session, dataset_id: str | None, limit: int) -> dict[str, Any]:
    event_statement = select(
        PayloadEvent.host,
        PayloadEvent.path,
        func.count(PayloadEvent.id),
        func.max(PayloadEvent.risk_score),
    ).group_by(PayloadEvent.host, PayloadEvent.path)
    vuln_statement = select(VulnerabilityCandidate)
    if dataset_id:
        event_statement = event_statement.where(PayloadEvent.dataset_id == dataset_id)
        vuln_statement = vuln_statement.where(VulnerabilityCandidate.dataset_id == dataset_id)
    surfaces = [
        {
            "host": host,
            "path": path,
            "event_count": count,
            "max_risk_score": max_risk,
        }
        for host, path, count, max_risk in db.execute(
            event_statement.order_by(func.max(PayloadEvent.risk_score).desc()).limit(limit)
        ).all()
    ]
    vulnerabilities = [
        {
            "id": item.id,
            "candidate_type": item.candidate_type,
            "target_component": item.target_component,
            "severity": item.severity,
            "confidence": item.confidence,
            "status": item.status,
        }
        for item in db.scalars(
            vuln_statement.order_by(VulnerabilityCandidate.confidence.desc()).limit(limit)
        ).all()
    ]
    return {
        "dataset_id": dataset_id,
        "top_surfaces": surfaces,
        "top_vulnerability_candidates": vulnerabilities,
    }


def _red_team_hypotheses(db: Session, dataset_id: str | None, limit: int) -> dict[str, Any]:
    statement = select(VulnerabilityCandidate).options(selectinload(VulnerabilityCandidate.event))
    if dataset_id:
        statement = statement.where(VulnerabilityCandidate.dataset_id == dataset_id)
    candidates = db.scalars(
        statement.order_by(VulnerabilityCandidate.confidence.desc(), VulnerabilityCandidate.created_at.desc()).limit(limit)
    ).all()
    hypotheses = []
    for candidate in candidates:
        evidence = candidate.evidence or {}
        hypotheses.append(
            {
                "vulnerability_id": candidate.id,
                "hypothesis": (
                    f"{candidate.target_component or 'unknown component'} 可能存在 "
                    f"{RED_TEAM_ATTACK_TYPES.get(candidate.candidate_type, candidate.candidate_type)} 风险。"
                ),
                "supporting_factors": evidence.get("confidence_factors") or [],
                "false_positive_risks": [
                    *list(evidence.get("false_positive_risks") or []),
                    *list(evidence.get("missing_context") or []),
                ][:6],
                "safe_validation_plan": evidence.get("recommended_validation_steps") or [],
                "prohibited_actions": [
                    "不构造破坏性 payload",
                    "不复放原始攻击 Query 或 Body",
                    "不访问未授权目标",
                    "不宣称利用成功，除非存在验证结果",
                ],
                "related_event": _event_payload(candidate.event),
            }
        )
    return {"dataset_id": dataset_id, "hypotheses": hypotheses}


def _risk_level(tool_name: str) -> str:
    if tool_name in HIGH_RISK_TOOLS:
        return "high_risk"
    if tool_name in WRITE_REVIEW_TOOLS:
        return "write_review"
    return "read_only"


def _dataset_csv_path(dataset: Dataset) -> Path | None:
    root = csv_storage_root()
    candidates: list[Path] = []
    if dataset.storage_path:
        candidates.append(Path(dataset.storage_path))
    candidates.append(root / dataset.filename)
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.is_file() and resolved.suffix.lower() == ".csv":
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            return resolved
    return None


def _read_dataset_csv_sample(db: Session, dataset_id: str, limit: int) -> dict[str, Any]:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    path = _dataset_csv_path(dataset)
    rows: list[str] = []
    if path:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            for line in handle:
                text = line.rstrip("\r\n")
                if text:
                    rows.append(text[:2000])
                if len(rows) >= limit:
                    break
    if not rows:
        events = db.scalars(
            select(PayloadEvent)
            .where(PayloadEvent.dataset_id == dataset_id)
            .order_by(PayloadEvent.row_number)
            .limit(limit)
        ).all()
        rows = [event.raw_payload[:2000] for event in events]
    return {
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "filename": dataset.filename,
            "status": dataset.status,
            "row_count": dataset.row_count,
            "file_sha256": dataset.file_sha256,
        },
        "storage_path": str(path) if path else None,
        "sample_count": len(rows),
        "sample_rows": rows,
    }


def execute_tool(
    db: Session,
    background_tasks: BackgroundTasks,
    name: str,
    arguments: dict[str, Any],
) -> Any:
    if name == "list_datasets":
        rows = db.scalars(select(Dataset).order_by(Dataset.created_at.desc()).limit(arguments.get("limit", 20))).all()
        return [
            {
                "id": item.id,
                "name": item.name,
                "filename": item.filename,
                "status": item.status,
                "row_count": item.row_count,
            }
            for item in rows
        ]
    if name == "get_dataset":
        dataset = db.get(Dataset, arguments["dataset_id"])
        if not dataset:
            raise HTTPException(status_code=404, detail="dataset not found")
        return {
            "id": dataset.id,
            "name": dataset.name,
            "filename": dataset.filename,
            "status": dataset.status,
            "row_count": dataset.row_count,
            "storage_available": _dataset_csv_path(dataset) is not None,
        }
    if name == "list_stored_csv_files":
        root = csv_storage_root()
        files = sorted(root.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
        return [
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "modified_at": path.stat().st_mtime,
            }
            for path in files[: arguments.get("limit", 20)]
        ]
    if name == "read_dataset_csv_sample":
        return _read_dataset_csv_sample(db, arguments["dataset_id"], min(max(arguments.get("limit", 12), 1), 50))
    if name == "hunt_query":
        filters = deterministic_filters(arguments["query"])
        if arguments.get("min_risk_score") is not None:
            filters = HuntFilters.model_validate(
                {**filters.model_dump(exclude_none=True), "min_risk_score": arguments["min_risk_score"]}
            )
        events, stats = execute_hunt(
            db,
            filters,
            arguments.get("dataset_id"),
            arguments.get("limit", 20),
            arguments.get("exclude_suppressed", True),
        )
        return {"events": [_event_payload(event) for event in events], **stats}
    if name == "attack_surface_map":
        return _attack_surface_map(db, arguments.get("dataset_id"), arguments.get("limit", 20))
    if name == "red_team_hypotheses":
        return _red_team_hypotheses(db, arguments.get("dataset_id"), arguments.get("limit", 10))
    if name == "get_event":
        event = db.scalar(
            select(PayloadEvent)
            .where(PayloadEvent.id == arguments["event_id"])
        )
        if not event:
            raise HTTPException(status_code=404, detail="event not found")
        return _event_payload(event)
    if name == "list_vulnerabilities":
        statement = select(VulnerabilityCandidate)
        if arguments.get("dataset_id"):
            statement = statement.where(VulnerabilityCandidate.dataset_id == arguments["dataset_id"])
        rows = db.scalars(statement.order_by(VulnerabilityCandidate.confidence.desc()).limit(arguments.get("limit", 20))).all()
        return [
            {
                "id": item.id,
                "candidate_type": item.candidate_type,
                "title": item.title,
                "severity": item.severity,
                "confidence": item.confidence,
                "status": item.status,
            }
            for item in rows
        ]
    if name == "get_vulnerability_analysis":
        vulnerability = db.scalar(
            select(VulnerabilityCandidate)
            .where(VulnerabilityCandidate.id == arguments["vulnerability_id"])
            .options(
                selectinload(VulnerabilityCandidate.event),
                selectinload(VulnerabilityCandidate.validation_runs).selectinload(ValidationRun.results),
            )
        )
        if not vulnerability:
            raise HTTPException(status_code=404, detail="vulnerability candidate not found")
        return _vulnerability_analysis(vulnerability)
    if name == "start_dataset_analysis":
        dataset = db.get(Dataset, arguments["dataset_id"])
        if not dataset:
            raise HTTPException(status_code=404, detail="dataset not found")
        active = db.scalar(
            select(AnalysisJob.id).where(
                AnalysisJob.dataset_id == dataset.id,
                AnalysisJob.status.in_(["queued", "running"]),
            )
        )
        if active:
            raise HTTPException(status_code=409, detail={"message": "analysis already running", "job_id": active})
        job = AnalysisJob(
            dataset_id=dataset.id,
            use_llm=arguments.get("use_llm", True),
            llm_scope=arguments.get("llm_scope", "suspicious"),
            force=arguments.get("force", False),
            total=dataset.row_count,
        )
        db.add(job)
        db.flush()
        background_tasks.add_task(run_analysis_job, job.id)
        return {"job_id": job.id, "dataset_id": dataset.id, "status": "queued"}
    raise HTTPException(status_code=422, detail=f"unsupported agent tool: {name}")

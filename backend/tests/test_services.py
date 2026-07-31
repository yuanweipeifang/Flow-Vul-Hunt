from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    AuthorizedTarget,
    CustomRule,
    Dataset,
    DetectionFinding,
    ExtractedFeature,
    PayloadEvent,
    ValidationResult,
    VulnerabilityCandidate,
)
from app.services.analysis_service import analyze_event
from app.services.comparison_service import compare_datasets
from app.services.dataset_service import ingest_dataset, store_csv_upload
from app.services.feature_extractor import extract_event_features
from app.services.incident_service import rebuild_incidents
from app.services.payload_inspector import inspect_payload
from app.services.report_service import generate_report
from app.services.validation_service import create_validation_run, target_allows_path


def test_real_sample_ingestion_and_analysis(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    sample = Path(__file__).parents[1] / "data" / "test_5+5_no_label.csv"

    with session_factory() as db:
        dataset = ingest_dataset(db, sample.name, None, sample.read_bytes())
        assert dataset.row_count == 10
        assert dataset.parsed_count == 10
        events = db.scalars(
            select(PayloadEvent).where(PayloadEvent.dataset_id == dataset.id).order_by(PayloadEvent.row_number)
        ).all()
        for event in events:
            analyze_event(db, event, use_llm=False, llm_scope="suspicious", force=False)
        db.commit()

        first_findings = db.scalars(
            select(DetectionFinding).where(DetectionFinding.event_id == events[0].id)
        ).all()
        assert any(item.attack_type == "command_injection" for item in first_findings)
        assert events[0].risk_score >= 60
        incidents = rebuild_incidents(db, dataset.id)
        assert all(incident.is_simulated is False for incident in incidents)
        assert incidents
        report = generate_report(db, incidents[0].id, use_llm=False)
        assert report.generator == "deterministic"
        assert report.content["evidence_event_ids"]
        assert "缺少时间" in report.content["limitations"][0]


def test_csv_upload_is_stored_and_dataset_tracks_path(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'stored.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("app.services.dataset_service.get_settings", lambda: type("S", (), {
        "max_payload_chars": 1000,
        "ingest_batch_size": 1000,
        "csv_storage_dir": str(tmp_path / "csv_uploads"),
    })())
    content = b'"GET /stored HTTP/1.1\\0D\\0AHost: app.test\\0D\\0A\\0D\\0A"\n'

    stored_path = store_csv_upload("payloads.csv", content)

    with session_factory() as db:
        dataset = ingest_dataset(db, stored_path.name, None, content, storage_path=str(stored_path))
        assert stored_path.exists()
        assert stored_path.read_bytes() == content
        assert dataset.filename == stored_path.name
        assert dataset.storage_path == str(stored_path)


def test_custom_rule_participates_in_analysis(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'rules.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as db:
        dataset = ingest_dataset(
            db,
            "custom.csv",
            None,
            b'"GET /download?template=freemarker_exec HTTP/1.1\\0D\\0AHost: app.test\\0D\\0A\\0D\\0A"\n',
        )
        db.add(
            CustomRule(
                rule_id="CUSTOM-TPL-001",
                name="Template execution marker",
                description="Detects a local template execution marker",
                attack_type="expression_injection",
                severity="high",
                confidence=0.9,
                pattern="freemarker_exec",
                enabled=True,
            )
        )
        db.commit()
        event = db.scalar(select(PayloadEvent).where(PayloadEvent.dataset_id == dataset.id))
        analyze_event(db, event, use_llm=False, llm_scope="suspicious", force=False)
        db.commit()

        findings = db.scalars(select(DetectionFinding).where(DetectionFinding.event_id == event.id)).all()
        custom = next(item for item in findings if item.detector_name == "CUSTOM-TPL-001")
        assert custom.detector_type == "custom_rule"
        assert event.risk_score >= 50


def test_payload_inspector_and_dataset_compare(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'compare.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as db:
        baseline = ingest_dataset(
            db,
            "baseline.csv",
            None,
            b'"GET /index HTTP/1.1\\0D\\0AHost: old.test\\0D\\0A\\0D\\0A"\n',
        )
        candidate = ingest_dataset(
            db,
            "candidate.csv",
            None,
            b'"GET /admin?next=http%3A%2F%2F169.254.169.254%2F HTTP/1.1\\0D\\0AHost: new.test\\0D\\0A\\0D\\0A"\n',
        )
        for event in db.scalars(select(PayloadEvent)).all():
            analyze_event(db, event, use_llm=False, llm_scope="suspicious", force=False)
        db.commit()

        inspected = inspect_payload(
            "GET /x?q=%253Cscript%253E HTTP/1.1\\0D\\0AHost: app.test\\0D\\0A\\0D\\0A"
        )
        assert inspected["decoded_variants"]["url_decoded_twice"]
        compared = compare_datasets(db, baseline.id, candidate.id)
        assert "new.test" in compared["new_hosts"]
        assert compared["counts"]["candidate_events"] == 1


def test_vulnerability_features_and_candidates_are_generated(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'vuln.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as db:
        dataset = ingest_dataset(
            db,
            "ssrf.csv",
            None,
            b'"GET /fetch?url=http%3A%2F%2F169.254.169.254%2Flatest HTTP/1.1\\0D\\0AHost: app.test\\0D\\0A\\0D\\0A"\n',
        )
        event = db.scalar(select(PayloadEvent).where(PayloadEvent.dataset_id == dataset.id))
        features = extract_event_features(event)
        assert features["internal_endpoints"]

        analyze_event(db, event, use_llm=False, llm_scope="suspicious", force=False)
        db.commit()

        stored = db.scalar(select(ExtractedFeature).where(ExtractedFeature.event_id == event.id))
        assert stored is not None
        candidate = db.scalar(select(VulnerabilityCandidate).where(VulnerabilityCandidate.event_id == event.id))
        assert candidate.candidate_type == "ssrf"
        assert candidate.confidence >= 0.5
        assert candidate.evidence["recommended_validation_steps"]


def test_authorized_target_scope_and_validation_audit(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'validation.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    class FakeResponse:
        status_code = 200
        content = b"ok"
        text = "ok"
        headers = {"content-type": "text/plain"}

        class Request:
            method = "HEAD"

        request = Request()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, headers=None):
            assert method == "HEAD"
            assert url == "https://app.test/api/vuln"
            return FakeResponse()

    monkeypatch.setattr("app.services.validation_service.httpx.Client", FakeClient)

    with session_factory() as db:
        dataset = ingest_dataset(
            db,
            "xss.csv",
            None,
            b'"GET /api/vuln?q=%3Cscript%3E HTTP/1.1\\0D\\0AHost: app.test\\0D\\0A\\0D\\0A"\n',
        )
        event = db.scalar(select(PayloadEvent).where(PayloadEvent.dataset_id == dataset.id))
        analyze_event(db, event, use_llm=False, llm_scope="suspicious", force=False)
        db.commit()
        vulnerability = db.scalar(select(VulnerabilityCandidate).where(VulnerabilityCandidate.event_id == event.id))
        target = AuthorizedTarget(
            name="app",
            scheme="https",
            host="app.test",
            port=None,
            path_scope="/api",
            enabled=True,
        )
        db.add(target)
        db.commit()
        assert target_allows_path(target, "/api/vuln")
        assert not target_allows_path(target, "/admin")

        run = create_validation_run(db, vulnerability, target, "HEAD", "/api/vuln", "tester")
        result = db.scalar(select(ValidationResult).where(ValidationResult.run_id == run.id))
        assert run.status == "completed"
        assert result.conclusion == "reachable"
        assert vulnerability.status == "validated"

        blocked = create_validation_run(db, vulnerability, target, "HEAD", "/admin", "tester")
        blocked_result = db.scalar(
            select(ValidationResult).where(ValidationResult.run_id == blocked.id)
        )
        assert blocked.status == "blocked"
        assert blocked_result.conclusion == "unauthorized_scope"

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import BackgroundTasks
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.datasets import analyze_datasets_batch
from app.api.agent import confirm_agent_session_tools
from app.api.hunting import hunt, run_saved_hunt_query, save_hunt_query
from app.api.vulnerabilities import analyze_vulnerability
from app.api.vulnerabilities import group_vulnerabilities
from app.audit import audit_log
from app.config import Settings
from app.database import Base
from app.errors import error_payload
from app.models import AgentMessage, AgentRun, AgentSession, AnalysisJob, AuditLog, Dataset, PayloadEvent, SavedHuntQuery, VulnerabilityCandidate, utcnow
from app.request_context import actor_var, request_id_var, role_var
from app.schemas import AgentChatRequest, AgentConfirmRequest, BatchAnalyzeRequest, CustomRuleCreate, HuntRequest, SavedHuntQueryCreate
from app.security import Actor, require_roles
from app.services.analysis_service import analyze_event, mark_stuck_jobs
from app.services.agent import agent_status, hermes_smoke_check, run_agent_chat
from app.services.dataset_service import ingest_dataset
from app.services.rule_service import dry_run_custom_rule
from app.services.vulnerability_service import ensure_event_vulnerability_analysis


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def test_error_payload_includes_request_id() -> None:
    request_id_var.set("req-test")
    assert error_payload("not_found", "missing") == {
        "code": "not_found",
        "message": "missing",
        "details": None,
        "request_id": "req-test",
    }


def test_permission_matrix_blocks_viewer_for_high_risk_action() -> None:
    dependency = require_roles("admin", "analyst")
    with pytest.raises(HTTPException) as exc:
        dependency(Actor(name="viewer", role="viewer", authenticated=True))
    assert exc.value.status_code == 403
    assert dependency(Actor(name="analyst", role="analyst", authenticated=True)).role == "analyst"


def test_settings_auth_defaults_keep_existing_construction_compatible() -> None:
    settings = Settings(
        app_name="test",
        app_env="test",
        database_url="sqlite:///:memory:",
        max_upload_bytes=1,
        max_payload_chars=1,
        llm_timeout_seconds=1,
        llm_max_retries=0,
        llm_max_input_chars=1,
        providers={},
        agent_routes={},
    )
    assert settings.auth_enabled is False
    assert settings.ingest_batch_size == 1000
    assert settings.stuck_job_timeout_seconds == 900
    assert settings.agent_enabled is False
    assert settings.agent_collaboration_enabled is True
    assert settings.agent_max_parallelism == 3
    assert settings.agent_require_verifier is True
    assert "hunt_query" in settings.agent_allowed_tools


def test_audit_log_uses_request_context(db_session) -> None:
    request_id_var.set("req-audit")
    actor_var.set("api_key:test")
    role_var.set("admin")
    audit_log(db_session, "dataset.upload", "dataset", "dataset-1", {"filename": "x.csv"})
    db_session.commit()
    record = db_session.query(AuditLog).one()
    assert record.request_id == "req-audit"
    assert record.actor == "api_key:test"
    assert record.role == "admin"


def test_agent_status_reports_project_local_hermes_isolation() -> None:
    settings = Settings(
        app_name="test",
        app_env="test",
        database_url="sqlite:///:memory:",
        max_upload_bytes=1,
        max_payload_chars=1,
        llm_timeout_seconds=1,
        llm_max_retries=0,
        llm_max_input_chars=1,
        providers={},
        agent_routes={},
        hermes_config_dir=".hermes/flow-vul-hunt",
        hermes_plugin_dir=".hermes/plugins/flow-vul-hunt",
    )
    status = agent_status(settings)
    assert status.hermes_isolated is True
    assert status.collaboration_enabled is True
    assert status.collaboration_mode == "multi_agent"
    assert "evidence_verifier" in status.agent_roles
    assert status.max_parallelism == 3
    unsafe = agent_status(
        Settings(
            app_name="test",
            app_env="test",
            database_url="sqlite:///:memory:",
            max_upload_bytes=1,
            max_payload_chars=1,
            llm_timeout_seconds=1,
            llm_max_retries=0,
            llm_max_input_chars=1,
            providers={},
            agent_routes={},
            hermes_config_dir="../shared-hermes",
            hermes_plugin_dir=".hermes/plugins/flow-vul-hunt",
        )
    )
    assert unsafe.hermes_isolated is False


def test_hermes_smoke_check_is_static_and_does_not_claim_live_e2e() -> None:
    settings = Settings(
        app_name="test",
        app_env="test",
        database_url="sqlite:///:memory:",
        max_upload_bytes=1,
        max_payload_chars=1,
        llm_timeout_seconds=1,
        llm_max_retries=0,
        llm_max_input_chars=1,
        providers={},
        agent_routes={},
        hermes_config_dir=".hermes/flow-vul-hunt",
        hermes_plugin_dir=".hermes/plugins/flow-vul-hunt",
    )
    result = hermes_smoke_check(settings)
    assert result["live_model_e2e_executed"] is False
    assert "ready_for_live_e2e" in result


def test_mark_stuck_jobs_marks_timed_out_running_job(db_session) -> None:
    job = AnalysisJob(
        dataset_id="dataset-1",
        status="running",
        phase="analyzing_event",
        last_heartbeat_at=utcnow() - timedelta(minutes=20),
    )
    db_session.add(job)
    db_session.commit()
    assert mark_stuck_jobs(db_session, timeout_seconds=60) == 1
    db_session.refresh(job)
    assert job.status == "failed"
    assert job.phase == "stuck_detected"
    assert job.error_count == 1


def test_batch_analyze_queues_available_datasets_and_skips_running(db_session) -> None:
    request_id_var.set("req-batch")
    actor_var.set("api_key:analyst")
    role_var.set("analyst")
    ready = Dataset(name="ready", filename="ready.csv", file_sha256="a" * 64, row_count=2, status="ready")
    busy = Dataset(name="busy", filename="busy.csv", file_sha256="b" * 64, row_count=3, status="ready")
    db_session.add_all([ready, busy])
    db_session.flush()
    running = AnalysisJob(dataset_id=busy.id, status="running", phase="analyzing_event")
    db_session.add(running)
    db_session.commit()

    result = analyze_datasets_batch(
        BatchAnalyzeRequest(dataset_ids=[ready.id, busy.id, "missing"], use_llm=False),
        BackgroundTasks(),
        db_session,
        Actor("api_key:analyst", "analyst", True),
    )

    assert result.requested == 3
    assert result.queued == 1
    assert result.skipped == 2
    jobs = db_session.scalars(select(AnalysisJob).where(AnalysisJob.dataset_id == ready.id)).all()
    assert len(jobs) == 1
    assert jobs[0].use_llm is False
    audit = db_session.scalars(select(AuditLog).where(AuditLog.action == "job.start")).one()
    assert audit.details["batch"] is True


def test_ingest_dataset_handles_large_batches(db_session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.dataset_service.get_settings", lambda: type("S", (), {
        "max_payload_chars": 1000,
        "ingest_batch_size": 2,
    })())
    rows = b"\n".join(
        [b'"GET /one HTTP/1.1\\0D\\0AHost: app.test\\0D\\0A\\0D\\0A"'] * 5
    )
    dataset = ingest_dataset(db_session, "batch.csv", None, rows)
    assert dataset.row_count == 5
    assert dataset.parsed_count == 5


def test_hunt_excludes_benign_events(db_session) -> None:
    dataset = Dataset(name="d", filename="d.csv", file_sha256="e" * 64, row_count=2, status="ready")
    db_session.add(dataset)
    db_session.flush()
    suppressed = PayloadEvent(
        dataset_id=dataset.id,
        row_number=1,
        raw_payload="GET /safe?q='or'1'='1 HTTP/1.1",
        decoded_payload="GET /safe?q='or'1'='1 HTTP/1.1",
        payload_hash="4" * 64,
        risk_score=80,
        verdict="benign",
    )
    active = PayloadEvent(
        dataset_id=dataset.id,
        row_number=2,
        raw_payload="GET /danger?q='or'1'='1 HTTP/1.1",
        decoded_payload="GET /danger?q='or'1'='1 HTTP/1.1",
        payload_hash="5" * 64,
        risk_score=90,
        verdict="suspicious",
    )
    db_session.add_all([suppressed, active])
    db_session.commit()

    result = hunt(
        HuntRequest(dataset_id=dataset.id, query="高危", use_llm=False),
        db_session,
        Actor("api_key:analyst", "analyst", True),
    )

    assert result.suppressed_events == 1
    assert [event.id for event in result.events] == [active.id]


def test_benign_event_does_not_create_vulnerability_candidate(db_session) -> None:
    dataset = Dataset(name="v", filename="v.csv", file_sha256="7" * 64, row_count=1, status="ready")
    db_session.add(dataset)
    db_session.flush()
    event = PayloadEvent(
        dataset_id=dataset.id,
        row_number=1,
        raw_payload="GET /fetch?url=http://169.254.169.254/latest HTTP/1.1",
        decoded_payload="GET /fetch?url=http://169.254.169.254/latest HTTP/1.1",
        payload_hash="8" * 64,
        verdict="benign",
    )
    db_session.add(event)
    db_session.commit()

    ensure_event_vulnerability_analysis(db_session, event, force=True)
    db_session.commit()

    assert event.verdict == "benign"
    assert db_session.scalar(select(VulnerabilityCandidate).where(VulnerabilityCandidate.event_id == event.id)) is None


def test_agent_executes_read_only_tools_and_blocks_high_risk_without_confirmation(db_session) -> None:
    request_id_var.set("req-agent")
    actor_var.set("api_key:analyst")
    role_var.set("analyst")
    settings = Settings(
        app_name="test",
        app_env="test",
        database_url="sqlite:///:memory:",
        max_upload_bytes=1,
        max_payload_chars=1,
        llm_timeout_seconds=1,
        llm_max_retries=0,
        llm_max_input_chars=1,
        providers={},
        agent_routes={},
        agent_enabled=True,
    )
    dataset = Dataset(name="agent", filename="agent.csv", file_sha256="9" * 64, row_count=1, status="ready")
    db_session.add(dataset)
    db_session.flush()
    db_session.add(
        PayloadEvent(
            dataset_id=dataset.id,
            row_number=1,
            raw_payload="GET /x?q='or'1'='1 HTTP/1.1",
            decoded_payload="GET /x?q='or'1'='1 HTTP/1.1",
            payload_hash="a" * 64,
            risk_score=75,
            verdict="suspicious",
        )
    )
    db_session.commit()

    result = run_agent_chat(
        AgentChatRequest(message="分析这个数据集的高危漏洞、攻击面和红队假设", dataset_id=dataset.id, auto_execute=False),
        db_session,
        BackgroundTasks(),
        Actor("api_key:analyst", "analyst", True),
        settings,
    )

    assert any(call.name == "hunt_query" and call.status == "executed" for call in result.tool_calls)
    assert any(call.name == "attack_surface_map" and call.status == "executed" for call in result.tool_calls)
    assert any(call.name == "red_team_hypotheses" and call.status == "executed" for call in result.tool_calls)
    assert any(call.name == "list_vulnerabilities" and call.status == "executed" for call in result.tool_calls)
    assert result.collaboration_mode == "multi_agent"
    assert result.llm_used is False
    names = {agent.agent_name for agent in result.agents}
    assert {"coordinator", "payload_analyst", "hunt_interpreter", "vulnerability_researcher", "evidence_verifier", "report_generator"} <= names
    assert result.consensus["confirmed_facts"]
    assert result.task_graph
    assert any(task.agent_name == "evidence_verifier" for task in result.task_graph)
    assert result.evidence_gaps
    blocked = [call for call in result.tool_calls if call.name == "start_dataset_analysis"]
    assert blocked and blocked[0].status == "blocked"
    assert result.requires_confirmation is True
    assert db_session.query(AuditLog).filter_by(action="agent.chat").count() == 1
    stored = db_session.get(AgentSession, result.session_id)
    assert stored.status == "waiting_confirmation"
    assert stored.task_graph
    assert len(stored.tool_calls) == len(result.tool_calls)
    assert db_session.query(AgentRun).filter_by(session_id=result.session_id).count() == 1
    assert db_session.query(AgentMessage).filter_by(session_id=result.session_id).count() >= 6

    confirmed = confirm_agent_session_tools(
        result.session_id,
        AgentConfirmRequest(tool_call_ids=[blocked[0].id]),
        BackgroundTasks(),
        db_session,
        Actor("api_key:analyst", "analyst", True),
    )

    assert any(call.name == "start_dataset_analysis" and call.status == "executed" for call in confirmed.tool_calls)
    assert confirmed.collaboration_mode == "multi_agent"
    assert any(agent.agent_name == "evidence_verifier" for agent in confirmed.agents)
    assert confirmed.requires_confirmation is False
    assert db_session.scalar(select(AnalysisJob).where(AnalysisJob.dataset_id == dataset.id)) is not None


def test_saved_hunt_query_can_be_run_and_records_suppression_stats(db_session) -> None:
    request_id_var.set("req-saved-hunt")
    actor_var.set("api_key:analyst")
    role_var.set("analyst")
    dataset = Dataset(name="hunt", filename="hunt.csv", file_sha256="b" * 64, row_count=2, status="ready")
    db_session.add(dataset)
    db_session.flush()
    suppressed = PayloadEvent(
        dataset_id=dataset.id,
        row_number=1,
        raw_payload="GET /safe?id=../../etc/passwd HTTP/1.1",
        decoded_payload="GET /safe?id=../../etc/passwd HTTP/1.1",
        payload_hash="c" * 64,
        risk_score=80,
        verdict="benign",
    )
    active = PayloadEvent(
        dataset_id=dataset.id,
        row_number=2,
        raw_payload="GET /download?id=../../etc/passwd HTTP/1.1",
        decoded_payload="GET /download?id=../../etc/passwd HTTP/1.1",
        payload_hash="d" * 64,
        risk_score=90,
        verdict="suspicious",
    )
    db_session.add_all([suppressed, active])
    db_session.commit()

    saved = save_hunt_query(
        SavedHuntQueryCreate(name="high risk", query="高危", dataset_id=dataset.id, use_llm=False),
        db_session,
        Actor("api_key:analyst", "analyst", True),
    )
    result = run_saved_hunt_query(saved.id, db_session, Actor("viewer", "viewer", True))

    assert [event.id for event in result.result.events] == [active.id]
    assert result.result.suppressed_events == 1
    stored = db_session.get(SavedHuntQuery, saved.id)
    assert stored.last_run_summary["suppressed_events"] == 1


def test_rule_dry_run_reports_match_samples(db_session) -> None:
    dataset = Dataset(name="d", filename="d.csv", file_sha256="d" * 64, row_count=1, status="ready")
    db_session.add(dataset)
    db_session.flush()
    db_session.add(
        PayloadEvent(
            dataset_id=dataset.id,
            row_number=1,
            raw_payload="GET /?q=needle HTTP/1.1",
            decoded_payload="GET /?q=needle HTTP/1.1",
            payload_hash="3" * 64,
        )
    )
    db_session.commit()

    result = dry_run_custom_rule(
        db_session,
        CustomRuleCreate(
            rule_id="DRY-RUN-1",
            name="dry run",
            description="dry run rule",
            attack_type="test",
            severity="low",
            confidence=0.5,
            pattern="needle",
        ),
        dataset.id,
        10,
    )

    assert result.tested == 1
    assert result.matched == 1
    assert result.samples[0].row_number == 1


def test_vulnerability_groups_aggregate_statuses(db_session) -> None:
    db_session.add_all(
        [
            VulnerabilityCandidate(
                dataset_id="dataset-1",
                event_id="event-1",
                candidate_type="ssrf",
                title="SSRF",
                target_component="app.test/fetch",
                severity="high",
                confidence=0.8,
                status="candidate",
                signature="s1",
                evidence={},
                impact="impact",
                validation_summary={},
            ),
            VulnerabilityCandidate(
                dataset_id="dataset-1",
                event_id="event-2",
                candidate_type="ssrf",
                title="SSRF",
                target_component="app.test/fetch",
                severity="critical",
                confidence=0.9,
                status="triaged",
                signature="s2",
                evidence={},
                impact="impact",
                validation_summary={},
            ),
        ]
    )
    db_session.commit()

    groups = group_vulnerabilities(
        dataset_id="dataset-1",
        limit=100,
        db=db_session,
        _actor=Actor("viewer", "viewer", True),
    )
    assert len(groups) == 1
    assert groups[0].count == 2
    assert groups[0].max_severity == "critical"
    assert groups[0].statuses == {"candidate": 1, "triaged": 1}


def test_vulnerability_analysis_view_includes_triage_context(db_session) -> None:
    dataset = Dataset(name="v", filename="v.csv", file_sha256="f" * 64, row_count=1, status="ready")
    db_session.add(dataset)
    db_session.flush()
    event = PayloadEvent(
        dataset_id=dataset.id,
        row_number=1,
        raw_payload="GET /fetch?url=http://169.254.169.254 HTTP/1.1",
        decoded_payload="GET /fetch?url=http://169.254.169.254 HTTP/1.1",
        payload_hash="6" * 64,
        risk_score=85,
        verdict="suspicious",
    )
    db_session.add(event)
    db_session.flush()
    candidate = VulnerabilityCandidate(
        dataset_id=dataset.id,
        event_id=event.id,
        candidate_type="ssrf",
        title="SSRF",
        target_component="app.test/fetch",
        severity="high",
        confidence=0.86,
        status="candidate",
        signature="s-analysis",
        evidence={
            "analysis_summary": "SSRF 候选分析",
            "confidence_factors": ["命中内网地址参数"],
            "false_positive_risks": ["可能只是客户端跳转参数。"],
            "recommended_validation_steps": ["确认参数是否会被服务端请求"],
        },
        impact="可能导致服务端访问内网资源。",
        validation_summary={},
    )
    db_session.add(candidate)
    db_session.commit()

    result = analyze_vulnerability(candidate.id, db_session, Actor("viewer", "viewer", True))

    assert result.analysis_summary == "SSRF 候选分析"
    assert result.related_event.id == event.id
    assert "命中内网地址参数" in result.confidence_factors
    assert result.false_positive_risks


def test_agent_chat_result_keeps_task_graph_and_fallback_answer(db_session) -> None:
    settings = Settings(
        app_name="test",
        app_env="test",
        database_url="sqlite:///:memory:",
        max_upload_bytes=1,
        max_payload_chars=1000,
        llm_timeout_seconds=1,
        llm_max_retries=0,
        llm_max_input_chars=1000,
        providers={},
        agent_routes={},
        agent_enabled=True,
        agent_collaboration_enabled=True,
    )
    dataset = Dataset(
        name="merge-contract",
        filename="merge.csv",
        file_sha256="f" * 64,
        row_count=1,
        status="ready",
    )
    db_session.add(dataset)
    db_session.flush()
    db_session.add(
        PayloadEvent(
            dataset_id=dataset.id,
            row_number=1,
            raw_payload="GET /search?q=hello HTTP/1.1",
            decoded_payload="GET /search?q=hello HTTP/1.1",
            payload_hash="1" * 64,
            risk_score=0,
            verdict="benign",
        )
    )
    db_session.commit()

    result = run_agent_chat(
        AgentChatRequest(
            message="Summarize this dataset",
            dataset_id=dataset.id,
            auto_execute=False,
        ),
        db_session,
        BackgroundTasks(),
        Actor("api_key:analyst", "analyst", True),
        settings,
    )

    assert result.answer
    assert result.task_graph
    assert result.collaboration_mode == "multi_agent"
    assert result.llm_used is False

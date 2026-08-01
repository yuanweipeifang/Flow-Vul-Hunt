from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def _load_launcher():
    launcher_path = Path(__file__).resolve().parents[2] / "run_backend.py"
    spec = importlib.util.spec_from_file_location("run_backend", launcher_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_starts_uvicorn_with_observable_defaults(monkeypatch) -> None:
    launcher = _load_launcher()
    calls = []
    monkeypatch.setattr(sys, "argv", ["run_backend.py"])
    monkeypatch.setattr(launcher.os, "chdir", lambda _path: None)
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append((args, kwargs)))

    launcher.main()

    assert calls == [
        (
            ("app.main:app",),
            {
                "host": "127.0.0.1",
                "port": 8000,
                "reload": False,
                "reload_dirs": None,
                "log_level": "info",
                "access_log": True,
            },
        )
    ]


def test_manual_review_routes_are_not_registered() -> None:
    from app.main import app

    paths = {path for route in app.routes if (path := getattr(route, "path", None))}
    assert "/api/events/bulk/annotate" not in paths
    assert "/api/events/{event_id}/annotations" not in paths


def test_run_migrations_commits_schema_version(tmp_path, monkeypatch) -> None:
    from app.config import Settings
    from app.database import run_migrations

    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    settings = Settings(
        app_name="test",
        app_env="test",
        database_url=database_url,
        max_upload_bytes=1,
        max_payload_chars=1,
        llm_timeout_seconds=1,
        llm_max_retries=0,
        llm_max_input_chars=1,
        providers={},
        agent_routes={},
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)

    run_migrations()

    engine = create_engine(database_url)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0009"
    assert "task_graph" in {column["name"] for column in inspect(engine).get_columns("agent_sessions")}

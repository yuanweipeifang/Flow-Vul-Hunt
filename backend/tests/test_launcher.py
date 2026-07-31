from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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

    paths = {route.path for route in app.routes}
    assert "/api/events/bulk/annotate" not in paths
    assert "/api/events/{event_id}/annotations" not in paths

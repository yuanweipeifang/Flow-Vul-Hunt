from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...config import Settings, get_settings
from ...schemas import AgentStatusOut
from .constants import AGENT_ROLES, PROJECT_ROOT


@dataclass(frozen=True)
class HermesIsolation:
    config_dir: Path
    plugin_dir: Path
    isolated: bool


def _inside_project(path: Path) -> bool:
    try:
        path.resolve().relative_to(PROJECT_ROOT.resolve())
        return True
    except ValueError:
        return False


def hermes_isolation(settings: Settings | None = None) -> HermesIsolation:
    settings = settings or get_settings()
    config_dir = (PROJECT_ROOT / settings.hermes_config_dir).resolve()
    plugin_dir = (PROJECT_ROOT / settings.hermes_plugin_dir).resolve()
    return HermesIsolation(
        config_dir=config_dir,
        plugin_dir=plugin_dir,
        isolated=_inside_project(config_dir) and _inside_project(plugin_dir),
    )


def agent_status(settings: Settings | None = None) -> AgentStatusOut:
    settings = settings or get_settings()
    isolation = hermes_isolation(settings)
    hermes_python_available = importlib.util.find_spec("hermes") is not None
    hermes_cli_available = shutil.which("hermes") is not None
    hermes_available = hermes_python_available or hermes_cli_available
    collaboration_enabled = settings.agent_collaboration_enabled
    return AgentStatusOut(
        enabled=settings.agent_enabled,
        runtime="hermes" if hermes_available and settings.llm_enabled else "flow_vul_hunt_multi_agent_local",
        hermes_available=hermes_available,
        hermes_python_available=hermes_python_available,
        hermes_cli_available=hermes_cli_available,
        hermes_config_dir=str(isolation.config_dir),
        hermes_plugin_dir=str(isolation.plugin_dir),
        hermes_isolated=isolation.isolated,
        allowed_tools=list(settings.agent_allowed_tools),
        require_confirmation=settings.agent_require_confirmation,
        collaboration_enabled=collaboration_enabled,
        collaboration_mode="multi_agent" if collaboration_enabled else "single_planner",
        agent_roles=AGENT_ROLES if collaboration_enabled else ["security_brain"],
        max_parallelism=settings.agent_max_parallelism if collaboration_enabled else 1,
        require_verifier=settings.agent_require_verifier,
    )


def hermes_smoke_check(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    status = agent_status(settings)
    isolation = hermes_isolation(settings)
    checks = {
        "hermes_available": status.hermes_available,
        "hermes_python_available": status.hermes_python_available,
        "hermes_cli_available": status.hermes_cli_available,
        "hermes_isolated": status.hermes_isolated,
        "config_dir_exists": isolation.config_dir.exists(),
        "plugin_dir_exists": isolation.plugin_dir.exists(),
        "system_prompt_exists": (isolation.config_dir / "system_prompt.md").exists(),
        "llm_configured": settings.llm_enabled,
        "live_model_e2e_executed": False,
    }
    checks["ready_for_live_e2e"] = all(
        [
            checks["hermes_available"],
            checks["hermes_isolated"],
            checks["config_dir_exists"],
            checks["plugin_dir_exists"],
            checks["system_prompt_exists"],
            checks["llm_configured"],
        ]
    )
    checks["note"] = (
        "Hermes/model smoke check is static-only; no provider network call was made."
        if not checks["ready_for_live_e2e"]
        else "Static readiness passed; run an explicit live model E2E with existing environment credentials."
    )
    return checks

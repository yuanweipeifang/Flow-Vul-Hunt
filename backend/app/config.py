from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env.agent", override=True)

PROVIDER_NAMES = ("deepseek", "bailian", "zhipu")
DEFAULT_AGENT_ROUTES = {
    "coordinator": ("deepseek",),
    "payload_analyst": ("deepseek",),
    "evidence_verifier": ("deepseek",),
    "hunt_interpreter": ("deepseek",),
    "vulnerability_researcher": ("deepseek",),
    "report_generator": ("deepseek",),
    "security_brain": ("deepseek",),
    "connection_test": ("deepseek",),
}
DEFAULT_AGENT_ALLOWED_TOOLS = (
    "list_datasets",
    "get_dataset",
    "hunt_query",
    "red_team_hypotheses",
    "attack_surface_map",
    "get_event",
    "list_vulnerabilities",
    "get_vulnerability_analysis",
    "start_dataset_analysis",
    "generate_incident_report",
    "read_dataset_csv_sample",
    "list_stored_csv_files",
)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _route_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    route = tuple(item.strip().lower() for item in raw.split(",") if item.strip()) if raw else default
    invalid = sorted(set(route) - set(PROVIDER_NAMES))
    if invalid:
        raise RuntimeError(f"{name} contains unsupported providers: {', '.join(invalid)}")
    if not route:
        raise RuntimeError(f"{name} must contain at least one provider")
    return route


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _api_keys_env() -> dict[str, str]:
    raw = os.getenv("API_KEYS", "")
    keys: dict[str, str] = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        token, _, role = item.partition(":")
        token = token.strip()
        role = (role.strip() or "analyst").lower()
        if role not in {"admin", "analyst", "viewer"}:
            raise RuntimeError("API_KEYS roles must be admin, analyst, or viewer")
        if token:
            keys[token] = role
    return keys


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    name: str
    base_url: str
    api_key: str
    model: str

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    database_url: str
    max_upload_bytes: int
    max_payload_chars: int
    llm_timeout_seconds: int
    llm_max_retries: int
    llm_max_input_chars: int
    providers: dict[str, ProviderSettings]
    agent_routes: dict[str, tuple[str, ...]]
    csv_storage_dir: str = "data/csv_uploads"
    ingest_batch_size: int = 1000
    auth_enabled: bool = False
    api_keys: dict[str, str] | None = None
    stuck_job_timeout_seconds: int = 15 * 60
    agent_enabled: bool = False
    agent_collaboration_enabled: bool = True
    agent_max_steps: int = 12
    agent_max_parallelism: int = 3
    agent_require_verifier: bool = True
    agent_require_confirmation: bool = True
    agent_allowed_tools: tuple[str, ...] = DEFAULT_AGENT_ALLOWED_TOOLS
    hermes_config_dir: str = ".hermes/flow-vul-hunt"
    hermes_plugin_dir: str = ".hermes/plugins/flow-vul-hunt"

    @property
    def llm_enabled(self) -> bool:
        return any(provider.enabled for provider in self.providers.values())

    def provider(self, name: str) -> ProviderSettings:
        try:
            return self.providers[name]
        except KeyError as exc:
            raise RuntimeError(f"unknown LLM provider: {name}") from exc

    def route_for(self, agent_name: str) -> tuple[str, ...]:
        try:
            return self.agent_routes[agent_name]
        except KeyError as exc:
            raise RuntimeError(f"no LLM route configured for agent: {agent_name}") from exc


@lru_cache
def get_settings() -> Settings:
    default_db = f"sqlite:///{(BASE_DIR / 'data' / 'flow_vul_hunt.db').as_posix()}"
    providers = {
        "deepseek": ProviderSettings(
            name="deepseek",
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        ),
        "bailian": ProviderSettings(
            name="bailian",
            base_url=os.getenv(
                "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ).rstrip("/"),
            api_key=os.getenv("BAILIAN_API_KEY", ""),
            model=os.getenv("BAILIAN_MODEL", "qwen3.7-plus"),
        ),
        "zhipu": ProviderSettings(
            name="zhipu",
            base_url=os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/"),
            api_key=os.getenv("ZHIPU_API_KEY", ""),
            model=os.getenv("ZHIPU_MODEL", "glm-5.2"),
        ),
    }
    routes = {
        "payload_analyst": _route_env(
            "LLM_ROUTE_PAYLOAD_ANALYST", DEFAULT_AGENT_ROUTES["payload_analyst"]
        ),
        "coordinator": _route_env(
            "LLM_ROUTE_COORDINATOR", DEFAULT_AGENT_ROUTES["coordinator"]
        ),
        "evidence_verifier": _route_env(
            "LLM_ROUTE_EVIDENCE_VERIFIER", DEFAULT_AGENT_ROUTES["evidence_verifier"]
        ),
        "hunt_interpreter": _route_env(
            "LLM_ROUTE_HUNT_INTERPRETER", DEFAULT_AGENT_ROUTES["hunt_interpreter"]
        ),
        "vulnerability_researcher": _route_env(
            "LLM_ROUTE_VULNERABILITY_RESEARCHER", DEFAULT_AGENT_ROUTES["vulnerability_researcher"]
        ),
        "report_generator": _route_env(
            "LLM_ROUTE_REPORT_GENERATOR", DEFAULT_AGENT_ROUTES["report_generator"]
        ),
        "security_brain": _route_env(
            "LLM_ROUTE_SECURITY_BRAIN", DEFAULT_AGENT_ROUTES["security_brain"]
        ),
        "connection_test": DEFAULT_AGENT_ROUTES["connection_test"],
    }
    return Settings(
        app_name=os.getenv("APP_NAME", "Flow Vul Hunt API"),
        app_env=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL", default_db),
        max_upload_bytes=_int_env("MAX_UPLOAD_BYTES", 50 * 1024 * 1024),
        csv_storage_dir=os.getenv("CSV_STORAGE_DIR", str(BASE_DIR / "data" / "csv_uploads")),
        max_payload_chars=_int_env("MAX_PAYLOAD_CHARS", 100_000),
        ingest_batch_size=_int_env("INGEST_BATCH_SIZE", 1000),
        llm_timeout_seconds=_int_env("LLM_TIMEOUT_SECONDS", 60),
        llm_max_retries=_int_env("LLM_MAX_RETRIES", 2),
        llm_max_input_chars=_int_env("LLM_MAX_INPUT_CHARS", 24_000),
        auth_enabled=_bool_env("AUTH_ENABLED", False),
        api_keys=_api_keys_env(),
        stuck_job_timeout_seconds=_int_env("STUCK_JOB_TIMEOUT_SECONDS", 15 * 60),
        agent_enabled=_bool_env("AGENT_ENABLED", False),
        agent_collaboration_enabled=_bool_env("AGENT_COLLABORATION_ENABLED", True),
        agent_max_steps=_int_env("AGENT_MAX_STEPS", 12),
        agent_max_parallelism=max(1, _int_env("AGENT_MAX_PARALLELISM", 3)),
        agent_require_verifier=_bool_env("AGENT_REQUIRE_VERIFIER", True),
        agent_require_confirmation=_bool_env("AGENT_REQUIRE_CONFIRMATION", True),
        agent_allowed_tools=_csv_env("AGENT_ALLOWED_TOOLS", DEFAULT_AGENT_ALLOWED_TOOLS),
        hermes_config_dir=os.getenv("FVH_HERMES_CONFIG_DIR", ".hermes/flow-vul-hunt"),
        hermes_plugin_dir=os.getenv("FVH_HERMES_PLUGIN_DIR", ".hermes/plugins/flow-vul-hunt"),
        providers=providers,
        agent_routes=routes,
    )

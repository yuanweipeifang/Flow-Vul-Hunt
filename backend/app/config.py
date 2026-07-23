from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

PROVIDER_NAMES = ("deepseek", "bailian", "zhipu")
DEFAULT_AGENT_ROUTES = {
    "payload_analyst": ("deepseek", "bailian", "zhipu"),
    "evidence_verifier": ("zhipu", "bailian", "deepseek"),
    "hunt_interpreter": ("bailian", "zhipu", "deepseek"),
    "report_generator": ("bailian", "deepseek", "zhipu"),
    "connection_test": ("deepseek", "bailian", "zhipu"),
}


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
        "evidence_verifier": _route_env(
            "LLM_ROUTE_EVIDENCE_VERIFIER", DEFAULT_AGENT_ROUTES["evidence_verifier"]
        ),
        "hunt_interpreter": _route_env(
            "LLM_ROUTE_HUNT_INTERPRETER", DEFAULT_AGENT_ROUTES["hunt_interpreter"]
        ),
        "report_generator": _route_env(
            "LLM_ROUTE_REPORT_GENERATOR", DEFAULT_AGENT_ROUTES["report_generator"]
        ),
        "connection_test": DEFAULT_AGENT_ROUTES["connection_test"],
    }
    return Settings(
        app_name=os.getenv("APP_NAME", "Flow Vul Hunt API"),
        app_env=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL", default_db),
        max_upload_bytes=_int_env("MAX_UPLOAD_BYTES", 50 * 1024 * 1024),
        max_payload_chars=_int_env("MAX_PAYLOAD_CHARS", 100_000),
        llm_timeout_seconds=_int_env("LLM_TIMEOUT_SECONDS", 60),
        llm_max_retries=_int_env("LLM_MAX_RETRIES", 2),
        llm_max_input_chars=_int_env("LLM_MAX_INPUT_CHARS", 24_000),
        providers=providers,
        agent_routes=routes,
    )

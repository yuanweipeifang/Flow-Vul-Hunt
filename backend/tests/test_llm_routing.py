from pydantic import BaseModel

from app.config import ProviderSettings, Settings
from app.llm.gateway import GatewayResult, LLMGateway, LLMResponseError, LLMUnavailableError


class Result(BaseModel):
    status: str


def make_settings(deepseek_key: str = "", bailian_key: str = "") -> Settings:
    providers = {
        "deepseek": ProviderSettings("deepseek", "https://deepseek.test", deepseek_key, "deepseek-test"),
        "bailian": ProviderSettings("bailian", "https://bailian.test", bailian_key, "qwen-test"),
        "zhipu": ProviderSettings("zhipu", "https://zhipu.test", "", "glm-test"),
    }
    routes = {
        "payload_analyst": ("deepseek", "bailian", "zhipu"),
        "evidence_verifier": ("zhipu", "bailian", "deepseek"),
        "hunt_interpreter": ("bailian", "zhipu", "deepseek"),
        "report_generator": ("bailian", "deepseek", "zhipu"),
        "connection_test": ("deepseek", "bailian", "zhipu"),
    }
    return Settings(
        app_name="test",
        app_env="test",
        database_url="sqlite:///:memory:",
        max_upload_bytes=1000,
        max_payload_chars=1000,
        llm_timeout_seconds=1,
        llm_max_retries=0,
        llm_max_input_chars=1000,
        providers=providers,
        agent_routes=routes,
    )


def test_route_skips_unconfigured_providers_and_fails_over(monkeypatch) -> None:
    gateway = LLMGateway(make_settings(deepseek_key="key-1", bailian_key="key-2"))
    called: list[str] = []

    def fake_call(provider, _system, _serialized, _schema):
        called.append(provider.name)
        if provider.name == "deepseek":
            raise LLMResponseError("temporary failure")
        return GatewayResult(
            data=Result(status="ok"),
            provider_name=provider.name,
            model_name=provider.model,
            request_hash="hash",
            token_usage={},
            latency_ms=1,
        )

    monkeypatch.setattr(gateway, "_call_provider", fake_call)
    result = gateway.complete_json("system", {"value": 1}, Result, agent_name="payload_analyst")
    assert called == ["deepseek", "bailian"]
    assert result.provider_name == "bailian"


def test_route_without_any_key_is_explicitly_unavailable() -> None:
    gateway = LLMGateway(make_settings())
    try:
        gateway.complete_json("system", {}, Result, agent_name="payload_analyst")
    except LLMUnavailableError as exc:
        assert "no configured API key" in str(exc)
    else:
        raise AssertionError("expected LLMUnavailableError")

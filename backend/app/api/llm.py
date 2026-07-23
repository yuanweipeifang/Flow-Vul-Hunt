from __future__ import annotations

from fastapi import APIRouter

from ..config import PROVIDER_NAMES, get_settings
from ..llm.gateway import LLMGateway, LLMResponseError, LLMUnavailableError
from ..llm.schemas import ConnectionTestResult
from ..schemas import ProviderTestRequest, ProviderTestResult


router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/providers")
def list_providers() -> dict:
    settings = get_settings()
    return {
        "providers": [
            {
                "name": provider.name,
                "configured": provider.enabled,
                "base_url": provider.base_url,
                "model": provider.model,
            }
            for provider in settings.providers.values()
        ],
        "agent_routes": {name: list(route) for name, route in settings.agent_routes.items()},
    }


@router.post("/test", response_model=list[ProviderTestResult])
def test_providers(request: ProviderTestRequest) -> list[ProviderTestResult]:
    settings = get_settings()
    names = request.providers or list(PROVIDER_NAMES)
    results: list[ProviderTestResult] = []
    for name in names:
        provider = settings.provider(name)
        if not provider.enabled:
            results.append(
                ProviderTestResult(
                    provider=name,
                    configured=False,
                    success=False,
                    model=provider.model,
                    error=f"{name.upper()}_API_KEY is not configured",
                )
            )
            continue
        try:
            call = LLMGateway(settings).complete_json(
                "Return only the JSON object {\"status\":\"ok\"}.",
                {"operation": "connection_test"},
                ConnectionTestResult,
                agent_name="connection_test",
                provider_override=(name,),
            )
            results.append(
                ProviderTestResult(
                    provider=name,
                    configured=True,
                    success=True,
                    model=call.model_name,
                    latency_ms=call.latency_ms,
                    token_usage=call.token_usage,
                )
            )
        except (LLMUnavailableError, LLMResponseError) as exc:
            results.append(
                ProviderTestResult(
                    provider=name,
                    configured=True,
                    success=False,
                    model=provider.model,
                    error=str(exc)[:2000],
                )
            )
    return results

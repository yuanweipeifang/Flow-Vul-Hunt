from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import ProviderSettings, Settings, get_settings


T = TypeVar("T", bound=BaseModel)


class LLMUnavailableError(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


@dataclass(slots=True)
class GatewayResult:
    data: BaseModel
    provider_name: str
    model_name: str
    request_hash: str
    token_usage: dict[str, Any]
    latency_ms: int


def _debug_event(hypothesis_id: str, location: str, msg: str, data: dict[str, Any] | None = None) -> None:
    payload = {
        "sessionId": "agent-chat-stall",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": location,
        "msg": f"[DEBUG] {msg}",
        "data": data or {},
    }
    url = os.getenv("DEBUG_SERVER_URL", "").strip()
    try:
        with open(".dbg/agent-chat-stall.env", encoding="utf-8") as env_file:
            for line in env_file:
                if line.startswith("DEBUG_SERVER_URL="):
                    url = line.split("=", 1)[1].strip() or url
    except Exception:
        pass
    if not url:
        return
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=1,
        ).read()
    except Exception:
        pass


class LLMGateway:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def complete_json(
        self,
        system_prompt: str,
        payload: dict[str, Any],
        schema: type[T],
        agent_name: str = "payload_analyst",
        provider_override: tuple[str, ...] | None = None,
    ) -> GatewayResult:
        route = provider_override or self.settings.route_for(agent_name)
        enabled = [self.settings.provider(name) for name in route if self.settings.provider(name).enabled]
        if not enabled:
            raise LLMUnavailableError(
                f"no configured API key for route {agent_name}: {', '.join(route)}"
            )

        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        _debug_event(
            "C",
            "backend/app/llm/gateway.py:complete_json:start",
            "starting llm complete_json",
            {
                "agent_name": agent_name,
                "provider_route": list(route),
                "enabled_providers": [provider.name for provider in enabled],
                "serialized_len": len(serialized),
            },
        )
        if len(serialized) > self.settings.llm_max_input_chars:
            serialized = serialized[: self.settings.llm_max_input_chars] + "\n[TRUNCATED BY SERVER]"
            _debug_event(
                "C",
                "backend/app/llm/gateway.py:complete_json:truncated",
                "truncated llm payload",
                {"agent_name": agent_name, "truncated_len": len(serialized)},
            )

        provider_errors: list[str] = []
        for provider in enabled:
            try:
                _debug_event(
                    "C",
                    f"backend/app/llm/gateway.py:complete_json:provider:{provider.name}",
                    "calling llm provider",
                    {"agent_name": agent_name, "provider": provider.name, "model": provider.model},
                )
                return self._call_provider(provider, system_prompt, serialized, schema)
            except LLMResponseError as exc:
                provider_errors.append(f"{provider.name}: {exc}")
                _debug_event(
                    "C",
                    f"backend/app/llm/gateway.py:complete_json:provider_error:{provider.name}",
                    "llm provider failed",
                    {"agent_name": agent_name, "provider": provider.name, "error": str(exc)[:500]},
                )
        raise LLMResponseError("all configured providers failed; " + " | ".join(provider_errors))

    def _call_provider(
        self,
        provider: ProviderSettings,
        system_prompt: str,
        serialized: str,
        schema: type[T],
    ) -> GatewayResult:
        request_hash = hashlib.sha256(
            (provider.name + provider.model + system_prompt + serialized).encode("utf-8")
        ).hexdigest()
        body = {
            "model": provider.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": serialized},
            ],
            "response_format": {"type": "json_object"},
        }
        started = time.monotonic()
        last_error: Exception | str | None = None
        response_format_enabled = True

        with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
            for attempt in range(self.settings.llm_max_retries + 1):
                try:
                    _debug_event(
                        "C",
                        f"backend/app/llm/gateway.py:_call_provider:attempt:{provider.name}",
                        "starting llm request attempt",
                        {"provider": provider.name, "attempt": attempt + 1, "response_format": response_format_enabled},
                    )
                    response = client.post(
                        f"{provider.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {provider.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    if response.status_code == 400 and response_format_enabled:
                        # Some OpenAI-compatible deployments rely on prompt-enforced JSON only.
                        body.pop("response_format", None)
                        response_format_enabled = False
                        last_error = "provider rejected response_format; retrying without it"
                        continue
                    response.raise_for_status()
                    raw = response.json()
                    content = raw["choices"][0]["message"]["content"]
                    parsed = self._parse_json(content)
                    validated = schema.model_validate(parsed)
                    _debug_event(
                        "C",
                        f"backend/app/llm/gateway.py:_call_provider:success:{provider.name}",
                        "llm request succeeded",
                        {
                            "provider": provider.name,
                            "attempt": attempt + 1,
                            "latency_ms": round((time.monotonic() - started) * 1000),
                        },
                    )
                    return GatewayResult(
                        data=validated,
                        provider_name=provider.name,
                        model_name=provider.model,
                        request_hash=request_hash,
                        token_usage=raw.get("usage") or {},
                        latency_ms=round((time.monotonic() - started) * 1000),
                    )
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    last_error = f"HTTP {status}: {exc.response.text[:500]}"
                    _debug_event(
                        "C",
                        f"backend/app/llm/gateway.py:_call_provider:http_error:{provider.name}",
                        "llm request returned http error",
                        {"provider": provider.name, "attempt": attempt + 1, "status": status},
                    )
                    if status in {401, 403, 404}:
                        break
                except (
                    httpx.HTTPError,
                    KeyError,
                    IndexError,
                    TypeError,
                    json.JSONDecodeError,
                    ValidationError,
                    LLMResponseError,
                ) as exc:
                    last_error = exc
                    _debug_event(
                        "C",
                        f"backend/app/llm/gateway.py:_call_provider:exception:{provider.name}",
                        "llm request raised exception",
                        {
                            "provider": provider.name,
                            "attempt": attempt + 1,
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:500],
                        },
                    )
                if attempt < self.settings.llm_max_retries:
                    time.sleep(min(2 ** attempt, 4))
        raise LLMResponseError(f"request failed: {last_error}")

    @staticmethod
    def _parse_json(content: Any) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise LLMResponseError("model content is not text or JSON")
        value = content.strip()
        if value.startswith("```"):
            lines = value.splitlines()
            value = "\n".join(lines[1:-1])
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise LLMResponseError("model output must be a JSON object")
        return parsed

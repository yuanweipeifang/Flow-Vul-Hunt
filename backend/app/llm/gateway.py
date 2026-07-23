from __future__ import annotations

import hashlib
import json
import time
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
        if len(serialized) > self.settings.llm_max_input_chars:
            serialized = serialized[: self.settings.llm_max_input_chars] + "\n[TRUNCATED BY SERVER]"

        provider_errors: list[str] = []
        for provider in enabled:
            try:
                return self._call_provider(provider, system_prompt, serialized, schema)
            except LLMResponseError as exc:
                provider_errors.append(f"{provider.name}: {exc}")
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

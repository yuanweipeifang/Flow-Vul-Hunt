from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PayloadInspectRequest(BaseModel):
    payload: str = Field(min_length=1, max_length=100_000)


class PayloadInspectResult(BaseModel):
    parsed: dict[str, Any]
    decoded_variants: dict[str, str | None]
    warnings: list[str] = Field(default_factory=list)

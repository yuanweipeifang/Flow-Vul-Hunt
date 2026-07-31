from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .base import ORMModel
from .events import EventSummary


class HuntRequest(BaseModel):
    dataset_id: str | None = None
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=50, ge=1, le=200)
    use_llm: bool = True
    exclude_suppressed: bool = True


class HuntResult(BaseModel):
    interpreted_filters: dict[str, Any]
    events: list[EventSummary]
    summary: str | None = None
    llm_used: bool = False
    warning: str | None = None
    matched_events: int = 0
    suppressed_events: int = 0
    suppression_policy: str | None = None


class SavedHuntQueryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=2000)
    dataset_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    use_llm: bool = True
    exclude_suppressed: bool = True
    limit: int = Field(default=50, ge=1, le=200)


class SavedHuntQueryOut(ORMModel):
    id: str
    name: str
    query: str
    dataset_id: str | None
    filters: dict[str, Any]
    tags: list[str]
    created_by: str | None
    last_run_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SavedHuntRunResult(BaseModel):
    saved_query: SavedHuntQueryOut
    result: HuntResult

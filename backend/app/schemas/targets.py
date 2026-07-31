from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .base import ORMModel


class AuthorizedTargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scheme: Literal["http", "https"]
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    path_scope: str = Field(default="/", min_length=1, max_length=512)
    enabled: bool = True
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("path_scope")
    @classmethod
    def normalize_path_scope(cls, value: str) -> str:
        value = value.strip() or "/"
        return value if value.startswith("/") else f"/{value}"


class AuthorizedTargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    scheme: Literal["http", "https"] | None = None
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    path_scope: str | None = Field(default=None, min_length=1, max_length=512)
    enabled: bool | None = None
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("host")
    @classmethod
    def normalize_optional_host(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("path_scope")
    @classmethod
    def normalize_optional_path_scope(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip() or "/"
        return value if value.startswith("/") else f"/{value}"


class AuthorizedTargetOut(ORMModel):
    id: str
    name: str
    scheme: str
    host: str
    port: int | None
    path_scope: str
    enabled: bool
    note: str | None
    created_at: datetime
    updated_at: datetime

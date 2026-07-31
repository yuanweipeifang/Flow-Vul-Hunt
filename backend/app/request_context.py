from __future__ import annotations

from contextvars import ContextVar


request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
actor_var: ContextVar[str] = ContextVar("actor", default="anonymous")
role_var: ContextVar[str] = ContextVar("role", default="anonymous")


def get_request_id() -> str | None:
    return request_id_var.get()


def get_actor() -> str:
    return actor_var.get()


def get_role() -> str:
    return role_var.get()

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from .config import get_settings
from .request_context import actor_var, role_var


ROLE_ORDER = {"viewer": 1, "analyst": 2, "admin": 3}


@dataclass(frozen=True)
class Actor:
    name: str
    role: str
    authenticated: bool = False


def _fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:12]


def get_actor(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> Actor:
    settings = get_settings()
    if not settings.auth_enabled:
        actor = Actor(name="system", role="admin", authenticated=False)
    else:
        if not x_api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing API key")
        role = (settings.api_keys or {}).get(x_api_key)
        if not role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid API key")
        actor = Actor(name=f"api_key:{_fingerprint(x_api_key)}", role=role, authenticated=True)
    actor_var.set(actor.name)
    role_var.set(actor.role)
    return actor


def require_roles(*allowed_roles: str):
    def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return actor

    return dependency

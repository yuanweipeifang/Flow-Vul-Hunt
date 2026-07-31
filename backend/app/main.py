from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import text

from .api import (
    agent,
    audit_logs,
    dashboard,
    datasets,
    events,
    exports,
    hunting,
    incidents,
    jobs,
    llm,
    payload,
    rules,
    system,
    targets,
    validation,
    vulnerabilities,
)
from .config import get_settings
from .database import SessionLocal, expected_migration_head, run_migrations
from .errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from .request_context import actor_var, request_id_var, role_var
from .schemas import HealthOut

logger = logging.getLogger("flow_vul_hunt.requests")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Payload dataset threat hunting and evidence-based LLM analysis backend.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request_id_var.set(request_id)
    actor_var.set("anonymous")
    role_var.set("anonymous")
    started = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    latency_ms = int((perf_counter() - started) * 1000)
    logger.info(
        "request completed",
        extra={
            "request_id": request_id,
            "actor": actor_var.get(),
            "route": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    return response

app.include_router(datasets.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(incidents.router, prefix="/api")
app.include_router(hunting.router, prefix="/api")
app.include_router(llm.router, prefix="/api")
app.include_router(payload.router, prefix="/api")
app.include_router(targets.router, prefix="/api")
app.include_router(vulnerabilities.router, prefix="/api")
app.include_router(validation.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(exports.router, prefix="/api")
app.include_router(audit_logs.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(agent.router, prefix="/api")


@app.get("/health", response_model=HealthOut, tags=["system"])
def health() -> HealthOut:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
        writable = True
        try:
            db.execute(text("CREATE TEMP TABLE IF NOT EXISTS health_write_check (id INTEGER)"))
            db.execute(text("INSERT INTO health_write_check (id) VALUES (1)"))
            db.execute(text("DELETE FROM health_write_check"))
        except Exception:
            writable = False
        migration = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        recent_errors = db.execute(
            text("SELECT COUNT(*) FROM analysis_jobs WHERE last_error_at IS NOT NULL OR status = 'failed'")
        ).scalar_one()
    return HealthOut(
        status="ok" if writable else "degraded",
        database="sqlite",
        migrations={"current": migration, "expected": expected_migration_head()},
        database_writable=writable,
        recent_task_errors=recent_errors,
        llm_configured=settings.llm_enabled,
        llm_enabled=settings.llm_enabled,
        providers=[
            {
                "name": provider.name,
                "configured": provider.enabled,
                "base_url": provider.base_url,
                "model": provider.model,
            }
            for provider in settings.providers.values()
        ],
        agent_routes={name: list(route) for name, route in settings.agent_routes.items()},
    )

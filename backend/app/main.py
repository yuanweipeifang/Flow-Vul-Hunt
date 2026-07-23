from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .api import (
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
    targets,
    validation,
    vulnerabilities,
)
from .config import get_settings
from .database import SessionLocal, run_migrations
from .schemas import HealthOut


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


@app.get("/health", response_model=HealthOut, tags=["system"])
def health() -> HealthOut:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return HealthOut(
        status="ok",
        database="sqlite",
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

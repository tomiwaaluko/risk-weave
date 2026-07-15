import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Literal

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from riskweave_api.accounting.service import GeminiAccountingService
from riskweave_api.extraction.shock_parser import GeminiShockParser
from riskweave_api.ingestion.database import session_factory
from riskweave_api.observability import configure_logging, scrub_secrets
from riskweave_api.observability.middleware import StructuredLoggingMiddleware
from riskweave_api.postgres_scenario_store import PostgresScenarioStore
from riskweave_api.routers import (
    accounting,
    graph,
    observability,
    registry,
    scenarios,
    slider,
    spike,
)
from riskweave_api.scenario_store import InMemoryScenarioStore, ScenarioStore
from riskweave_api.security import RateLimiter
from riskweave_api.settings import Settings

configure_logging()
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"]


def _build_store(settings: Settings) -> ScenarioStore:
    """Select the ScenarioStore backend the settings ask for (RIS-30)."""
    if settings.scenario_store_backend == "postgres":
        return PostgresScenarioStore(session_factory(settings.database_url))
    return InMemoryScenarioStore()


def _check_postgres_connectivity(settings: Settings) -> bool:
    """Probe the configured Postgres backend with `SELECT 1`. Logs the transition.

    Only relevant when ``scenario_store_backend`` is "postgres" (Railway,
    ADR-008); the in-memory backend used locally/CI has nothing to probe.
    """
    try:
        factory = session_factory(settings.database_url)
        with factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        logger.error(
            "postgres connectivity check failed at startup",
            extra={"fields": {"component": "postgres", "state": "unavailable"}},
            exc_info=True,
        )
        return False
    logger.info(
        "postgres connected",
        extra={"fields": {"component": "postgres", "state": "connected"}},
    )
    return True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    app.state.settings = settings
    app.state.store = _build_store(settings)
    # RIS-34 / RW-DATA-005: DATABASE_URL is always configured, independent of
    # the scenario-store backend, so Gemini cost accounting always has
    # somewhere to write regardless of "memory" vs "postgres" scenario storage.
    app.state.db_session_factory = session_factory(settings.database_url)
    app.state.accounting = GeminiAccountingService(
        soft_daily_budget_usd=Decimal(str(settings.gemini_daily_soft_budget_usd)),
        hard_daily_budget_usd=Decimal(str(settings.gemini_daily_hard_budget_usd)),
    )
    app.state.shock_parser = GeminiShockParser.from_settings(
        settings,
        accounting=app.state.accounting,
        accounting_session_factory=app.state.db_session_factory,
    )
    app.state.rate_limiter = RateLimiter()
    app.state.slider_connections = 0

    if settings.scenario_store_backend == "postgres":
        app.state.postgres_connected = _check_postgres_connectivity(settings)
    else:
        app.state.postgres_connected = None  # not applicable to the in-memory backend

    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        app.state.redis = redis_client
        app.state.redis_connected = True
        logger.info(
            "redis connected",
            extra={"fields": {"component": "redis", "state": "connected"}},
        )
    except Exception as exc:
        # Fail quiet, not fail invisible: the service still starts and runs
        # uncached/degraded (RW-NFR-004 is best-effort), but that degradation
        # is now a structured, alertable log line instead of a swallowed
        # exception (RIS-33 — this replaces the previous bare `except: pass`).
        redis_client = None
        app.state.redis = None
        app.state.redis_connected = False
        logger.error(
            "redis connection failed at startup; running degraded/uncached",
            extra={"fields": {"component": "redis", "state": "unavailable"}},
        )
        logger.debug("redis connection error detail: %s", scrub_secrets(str(exc)))

    yield

    if redis_client is not None:
        await redis_client.aclose()


app = FastAPI(title="RiskWeave API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=os.getenv(
        "CORS_ALLOW_ORIGIN_REGEX",
        Settings.model_fields["cors_allow_origin_regex"].default,
    ),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(StructuredLoggingMiddleware)

app.include_router(scenarios.router)
app.include_router(slider.router)
app.include_router(registry.router)
app.include_router(spike.router)
app.include_router(graph.router)
app.include_router(accounting.router)
app.include_router(observability.router)


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health() -> HealthResponse:
    """Report process health for Docker Compose and CI smoke checks."""
    return HealthResponse(status="ok")

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from riskweave_api.extraction.shock_parser import GeminiShockParser
from riskweave_api.routers import graph, registry, scenarios, slider, spike
from riskweave_api.scenario_store import ScenarioStore
from riskweave_api.security import RateLimiter
from riskweave_api.settings import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    app.state.settings = settings
    app.state.store = ScenarioStore()
    app.state.shock_parser = GeminiShockParser.from_settings(settings)
    app.state.rate_limiter = RateLimiter()
    app.state.slider_connections = 0

    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        app.state.redis = redis_client
    except Exception:
        app.state.redis = None

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

app.include_router(scenarios.router)
app.include_router(slider.router)
app.include_router(registry.router)
app.include_router(spike.router)
app.include_router(graph.router)


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health() -> HealthResponse:
    """Report process health for Docker Compose and CI smoke checks."""
    return HealthResponse(status="ok")

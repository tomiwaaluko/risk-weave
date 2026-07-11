from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import redis.asyncio as aioredis
from fastapi import FastAPI
from pydantic import BaseModel

from riskweave_api.routers import registry, scenarios, slider
from riskweave_api.scenario_store import ScenarioStore
from riskweave_api.settings import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    app.state.settings = settings
    app.state.store = ScenarioStore()

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

app.include_router(scenarios.router)
app.include_router(slider.router)
app.include_router(registry.router)


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health() -> HealthResponse:
    """Report process health for Docker Compose and CI smoke checks."""
    return HealthResponse(status="ok")

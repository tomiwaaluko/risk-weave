from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from riskweave_api.settings import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.settings = Settings()
    yield


app = FastAPI(title="RiskWeave API", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health() -> HealthResponse:
    """Report process health for Docker Compose and CI smoke checks."""
    return HealthResponse(status="ok")

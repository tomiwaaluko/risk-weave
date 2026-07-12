"""FastAPI dependency injection helpers."""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import FastAPI, Request

from riskweave.explain import ExplanationTransport

from .extraction.gemini import GeminiRestTransport
from .extraction.shock_parser import GeminiShockParser
from .scenario_store import ScenarioStore


def get_store(request: Request) -> ScenarioStore:
    return request.app.state.store


def get_explanation_transport(request: Request) -> ExplanationTransport:
    """Gemini transport for explanation generation (RIS-19).

    Tests inject a fake by setting ``app.state.gemini_transport``; otherwise the
    real REST transport is built from the server-only Gemini key so the demo
    path is a genuine Gemini call (`RW-AI-003`).
    """
    override = getattr(request.app.state, "gemini_transport", None)
    if override is not None:
        return override
    settings = request.app.state.settings
    return GeminiRestTransport(settings.gemini_api_key)


def get_shock_parser(request: Request) -> GeminiShockParser:
    return request.app.state.shock_parser


async def get_redis(request: Request) -> aioredis.Redis | None:
    return getattr(request.app.state, "redis", None)


def _get_store_direct(app: FastAPI) -> ScenarioStore:
    return app.state.store


async def _get_redis_direct(app: FastAPI) -> aioredis.Redis | None:
    return getattr(app.state, "redis", None)

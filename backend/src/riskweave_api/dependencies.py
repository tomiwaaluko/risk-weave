"""FastAPI dependency injection helpers."""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import FastAPI, Request

from .extraction.shock_parser import GeminiShockParser
from .scenario_store import ScenarioStore


def get_store(request: Request) -> ScenarioStore:
    return request.app.state.store


def get_shock_parser(request: Request) -> GeminiShockParser:
    return request.app.state.shock_parser


async def get_redis(request: Request) -> aioredis.Redis | None:
    return getattr(request.app.state, "redis", None)


def _get_store_direct(app: FastAPI) -> ScenarioStore:
    return app.state.store


async def _get_redis_direct(app: FastAPI) -> aioredis.Redis | None:
    return getattr(app.state, "redis", None)

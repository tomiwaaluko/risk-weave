"""Redis result cache for propagation runs (RW-NFR-004).

Cache key: (snapshot_id, graph_version, scenario_hash, severity_rounded)
where scenario_hash is SHA-256 over the canonical JSON of the scenario config
and severity is rounded to 2 decimal places (1 % steps).

All values are JSON-serialized RunResult blobs with a 1-hour TTL.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from .models import RunResult

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # seconds


def _severity_key(severity: float) -> str:
    return f"{severity:.2f}"


def make_cache_key(
    snapshot_id: str,
    graph_version: str,
    scenario_json: str,
    severity: float,
) -> str:
    scenario_hash = hashlib.sha256(scenario_json.encode()).hexdigest()[:16]
    return f"rw:run:{snapshot_id}:{graph_version}:{scenario_hash}:{_severity_key(severity)}"


async def get_cached(client: aioredis.Redis, key: str) -> RunResult | None:
    from .models import RunResult

    raw = await client.get(key)
    if raw is None:
        return None
    try:
        return RunResult.model_validate_json(raw)
    except Exception:
        logger.warning("cache deserialization failure for key %s; treating as miss", key)
        return None


async def set_cached(client: aioredis.Redis, key: str, result: RunResult) -> None:
    await client.set(key, result.model_dump_json(), ex=_CACHE_TTL)

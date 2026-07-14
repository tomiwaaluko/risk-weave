"""WebSocket endpoint for live severity-slider recompute (RW-FR-020, RW-NFR-002).

Protocol:
  client → {"severity": 0.45}
  server → SliderUpdate JSON

The in-memory graph snapshot for the scenario stays warm for the lifetime of
the connection. Repeated severity positions hit Redis before recomputing.
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from riskweave_api.cache import get_cached, make_cache_key, set_cached
from riskweave_api.dependencies import _get_redis_direct, _get_store_direct
from riskweave_api.models import SliderMessage, SliderUpdate
from riskweave_api.security import (
    new_slider_message_bucket,
    release_slider_connection,
    try_reserve_slider_connection,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["slider"])


@router.websocket("/scenarios/{scenario_id}/slider")
async def slider_ws(scenario_id: str, websocket: WebSocket) -> None:
    if not try_reserve_slider_connection(websocket.app.state):
        await websocket.close(code=4029, reason="too many slider connections")
        return

    await websocket.accept()
    store = _get_store_direct(websocket.app)
    redis = await _get_redis_direct(websocket.app)
    message_bucket = new_slider_message_bucket()

    try:
        try:
            store.get(scenario_id)
        except KeyError:
            await websocket.close(code=4004, reason="scenario not found")
            return

        config = store.get_config(scenario_id)
        record = store.get(scenario_id)
        config_json = json.dumps(config, sort_keys=True)

        while True:
            raw = await websocket.receive_text()
            if not message_bucket.consume():
                await websocket.send_text(json.dumps({"error": "rate limited"}))
                continue

            try:
                msg = SliderMessage.model_validate_json(raw)
            except ValidationError as exc:
                await websocket.send_text(json.dumps({"error": str(exc)}))
                continue

            severity = msg.severity
            cache_key = make_cache_key(
                record.snapshot_id,
                record.graph_version,
                config_json,
                severity,
            )

            cached_result = None
            if redis is not None:
                cached_result = await get_cached(redis, cache_key)

            if cached_result is not None:
                update = SliderUpdate(
                    severity=severity,
                    impacts=cached_result.impacts,
                    ranked_entity_ids=cached_result.ranked_entity_ids,
                    cached=True,
                    latency_ms=cached_result.latency_ms,
                )
                await websocket.send_text(update.model_dump_json())
                continue

            t0 = time.perf_counter()
            run_result, latency_ms = store.run(scenario_id, severity)
            total_ms = (time.perf_counter() - t0) * 1000.0

            if total_ms > 500:
                logger.warning(
                    "slider recompute exceeded 500 ms budget: %.1f ms scenario=%s severity=%.2f",
                    total_ms,
                    scenario_id,
                    severity,
                )
            else:
                logger.debug(
                    "slider recompute %.1f ms scenario=%s severity=%.2f",
                    total_ms,
                    scenario_id,
                    severity,
                )

            if redis is not None:
                await set_cached(redis, cache_key, run_result)

            update = SliderUpdate(
                severity=severity,
                impacts=run_result.impacts,
                ranked_entity_ids=run_result.ranked_entity_ids,
                cached=False,
                latency_ms=total_ms,
            )
            await websocket.send_text(update.model_dump_json())

    except WebSocketDisconnect:
        pass
    finally:
        release_slider_connection(websocket.app.state)

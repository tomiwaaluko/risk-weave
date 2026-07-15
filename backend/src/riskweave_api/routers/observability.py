"""Production latency metrics endpoint (RIS-33, `RW-NFR-002`, spec §15).

Read-only, unauthenticated (same trust level as `/health`) — the RIS-21
evaluation dashboard and any external monitor read production p50/p95
latency here without needing the API key gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from riskweave_api.observability import latency_snapshot

router = APIRouter(tags=["operations"])

#: The RW-NFR-002 slider-recompute budget, echoed back for dashboard reference.
SLIDER_RECOMPUTE_BUDGET_MS = 500


class LatencyHistogramOut(BaseModel):
    count: int
    p50_ms: float | None
    p95_ms: float | None
    max_ms: float | None


class LatencyMetricsResponse(BaseModel):
    budget_ms: dict[str, int]
    histograms: dict[str, LatencyHistogramOut]


class ConnectivityResponse(BaseModel):
    redis_connected: bool | None
    postgres_connected: bool | None


@router.get("/metrics/latency", response_model=LatencyMetricsResponse)
def get_latency_metrics() -> LatencyMetricsResponse:
    """p50/p95/count for scenario parse, propagation recompute, and explanation generation."""
    snapshot = latency_snapshot()
    return LatencyMetricsResponse(
        budget_ms={"propagation_recompute": SLIDER_RECOMPUTE_BUDGET_MS},
        histograms={name: LatencyHistogramOut(**values) for name, values in snapshot.items()},
    )


@router.get("/metrics/connectivity", response_model=ConnectivityResponse)
def get_connectivity(request: Request) -> ConnectivityResponse:
    """Last-known Redis/Postgres connectivity state, set once at process startup.

    ``None`` means "not applicable" (e.g. the in-memory scenario store has no
    Postgres to probe). This mirrors the structured connectivity log lines
    emitted in the lifespan so an alerting rule can poll state instead of
    parsing logs.
    """
    return ConnectivityResponse(
        redis_connected=getattr(request.app.state, "redis_connected", None),
        postgres_connected=getattr(request.app.state, "postgres_connected", None),
    )

"""Latency histograms and the /metrics/latency endpoint (RIS-33, RW-NFR-002)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from riskweave_api.main import app
from riskweave_api.observability.metrics import (
    PROPAGATION_RECOMPUTE,
    latency_snapshot,
    latency_timer,
    record_latency,
    reset_metrics,
)

_ENV = {
    "DATABASE_URL": "postgresql://riskweave:password@postgres:5432/riskweave",
    "NEO4J_URI": "bolt://neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "password",
    "REDIS_URL": "redis://redis:6379/0",
    "GEMINI_API_KEY": "test-placeholder",
}


@pytest.fixture(autouse=True)
def _isolate_metrics() -> None:
    reset_metrics()
    yield
    reset_metrics()


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestLatencyHistogram:
    def test_unknown_histogram_reports_empty_snapshot(self) -> None:
        assert latency_snapshot() == {}

    def test_records_count_and_percentiles(self) -> None:
        for value in [10, 20, 30, 40, 100]:
            record_latency("demo", value)
        snap = latency_snapshot()["demo"]
        assert snap["count"] == 5
        assert snap["p50_ms"] == 30
        assert snap["max_ms"] == 100

    def test_latency_timer_records_elapsed_time(self) -> None:
        with latency_timer("demo"):
            pass
        snap = latency_snapshot()["demo"]
        assert snap["count"] == 1
        assert snap["p50_ms"] is not None
        assert snap["p50_ms"] >= 0


class TestLatencyMetricsEndpoint:
    def test_returns_budget_and_empty_histograms_before_any_run(self, client: TestClient) -> None:
        response = client.get("/metrics/latency")
        assert response.status_code == 200
        body = response.json()
        assert body["budget_ms"]["propagation_recompute"] == 500
        assert body["histograms"] == {}

    def test_reports_recorded_samples(self, client: TestClient) -> None:
        record_latency(PROPAGATION_RECOMPUTE, 123.4)
        response = client.get("/metrics/latency")
        histogram = response.json()["histograms"][PROPAGATION_RECOMPUTE]
        assert histogram["count"] == 1
        assert histogram["p50_ms"] == 123.4

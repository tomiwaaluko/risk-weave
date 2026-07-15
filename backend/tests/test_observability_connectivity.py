"""Redis/Postgres connectivity failures at startup log, they don't vanish (RIS-33).

Regression coverage for the pattern called out in the ticket: the lifespan
used to swallow a Redis connection failure with a bare `except Exception:
app.state.redis = None`, so the service ran uncached/degraded with zero log
signal. It must now emit a structured, alertable log line.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from riskweave_api.main import app

_ENV = {
    "DATABASE_URL": "postgresql://riskweave:password@postgres:5432/riskweave",
    "NEO4J_URI": "bolt://neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "password",
    # Deliberately unreachable — nothing is listening on this port.
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "GEMINI_API_KEY": "test-placeholder",
}


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


def test_redis_startup_failure_logs_structured_error_and_still_serves(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="riskweave_api.main"), TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200, "the service must still start in degraded mode"

    error_records = [
        r
        for r in caplog.records
        if r.name == "riskweave_api.main" and getattr(r, "fields", {}).get("component") == "redis"
    ]
    assert error_records, "expected a structured redis connectivity error log"
    assert error_records[-1].fields["state"] == "unavailable"


def test_redis_connected_state_recorded_on_app_state(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="riskweave_api.main"), TestClient(app) as client:
        client.get("/health")
        assert app.state.redis_connected is False


def test_connectivity_endpoint_reports_redis_down(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="riskweave_api.main"), TestClient(app) as client:
        response = client.get("/metrics/connectivity")
    assert response.status_code == 200
    body = response.json()
    assert body["redis_connected"] is False
    # scenario_store_backend defaults to "memory" in this test env, so Postgres
    # is never probed and reports "not applicable" rather than a false failure.
    assert body["postgres_connected"] is None

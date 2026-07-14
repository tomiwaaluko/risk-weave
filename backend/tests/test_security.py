"""Auth, rate limiting, and the spike-endpoint gate for the public deployment.

Covers RIS-31 / ADR-010: anonymous mutating and Gemini-calling endpoints are
rejected once ``RISKWEAVE_API_KEY`` is configured, rate limits demonstrably
trigger, and the WebSocket connection cap protects the slider.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from riskweave_api.extraction.shock_parser import GeminiShockParser
from riskweave_api.main import app
from riskweave_api.security import (
    MAX_SLIDER_CONNECTIONS,
    RateLimiter,
    TokenBucket,
    release_slider_connection,
    require_api_key,
    try_reserve_slider_connection,
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
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def open_client() -> TestClient:
    """No RISKWEAVE_API_KEY configured — matches today's local/dev/CI behavior."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def keyed_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RISKWEAVE_API_KEY", "s3cret-test-key")
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# API key gate
# ---------------------------------------------------------------------------


def test_unset_api_key_leaves_mutating_endpoints_open(open_client: TestClient) -> None:
    resp = open_client.post("/graph/seed")
    assert resp.status_code == 201


def test_configured_key_rejects_anonymous_scenario_create(keyed_client: TestClient) -> None:
    resp = keyed_client.post(
        "/scenarios",
        json={
            "scenario_id": "s1",
            "snapshot_id": "snap-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 1.0}],
        },
    )
    assert resp.status_code == 401
    assert "secret" not in resp.text.lower()


def test_configured_key_rejects_wrong_bearer_token(keyed_client: TestClient) -> None:
    resp = keyed_client.post("/graph/seed", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401


def test_configured_key_accepts_correct_bearer_token(keyed_client: TestClient) -> None:
    resp = keyed_client.post("/graph/seed", headers={"Authorization": "Bearer s3cret-test-key"})
    assert resp.status_code == 201


def test_configured_key_rejects_anonymous_spike_seed(keyed_client: TestClient) -> None:
    resp = keyed_client.post("/spike/seed")
    assert resp.status_code == 401


def test_configured_key_rejects_anonymous_preset_parse(keyed_client: TestClient) -> None:
    resp = keyed_client.post("/scenarios/presets/cre/parse")
    assert resp.status_code == 401


def test_configured_key_rejects_anonymous_explanation(keyed_client: TestClient) -> None:
    resp = keyed_client.get("/scenarios/cre-demo/explanation/some-node")
    assert resp.status_code == 401


def test_configured_key_rejects_anonymous_freeform_parse(keyed_client: TestClient) -> None:
    resp = keyed_client.post("/scenarios/parse/live", json={"text": "CRE values fall 20%."})
    assert resp.status_code == 401


def test_configured_key_rejects_anonymous_qa(keyed_client: TestClient) -> None:
    resp = keyed_client.post(
        "/scenarios/cre-demo/qa", json={"question": "why?", "severity": 1.0, "audience": "analyst"}
    )
    assert resp.status_code == 401


def test_configured_key_does_not_gate_health(keyed_client: TestClient) -> None:
    resp = keyed_client.get("/health")
    assert resp.status_code == 200


def test_configured_key_does_not_gate_read_only_methodology(keyed_client: TestClient) -> None:
    resp = keyed_client.get("/graph/methodology")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_token_bucket_exhausts_then_refills() -> None:
    import time

    bucket = TokenBucket(capacity=2, refill_per_sec=1_000.0)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False  # burst exhausted
    time.sleep(0.01)  # ~10 tokens' worth at this refill rate
    assert bucket.consume() is True


def test_rate_limiter_tracks_ip_and_bucket_name_independently() -> None:
    limiter = RateLimiter()
    assert limiter.allow("gemini", "1.2.3.4", capacity=1, refill_per_sec=0.0) is True
    assert limiter.allow("gemini", "1.2.3.4", capacity=1, refill_per_sec=0.0) is False
    # A different IP gets its own bucket.
    assert limiter.allow("gemini", "5.6.7.8", capacity=1, refill_per_sec=0.0) is True
    # A different bucket name for the same IP is independent too.
    assert limiter.allow("default", "1.2.3.4", capacity=1, refill_per_sec=0.0) is True


class _FakeTransport:
    """Hermetic stand-in so the burst test never reaches the real Gemini API."""

    def create_interaction(self, **kwargs: object) -> dict[str, object]:
        return {"output_text": "not valid json", "usage": {}}


def test_gemini_rate_limit_triggers_before_gemini_quota_damage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Burst past the tight Gemini-endpoint budget and confirm a 429, not a Gemini call."""
    monkeypatch.setenv("RISKWEAVE_API_KEY", "s3cret-test-key")
    with TestClient(app) as client:
        client.app.state.shock_parser = GeminiShockParser(_FakeTransport())
        headers = {"Authorization": "Bearer s3cret-test-key"}
        statuses = [
            client.post("/scenarios/presets/cre/parse", headers=headers).status_code
            for _ in range(10)
        ]
    assert 429 in statuses, f"expected a 429 within a 10-request burst, got {statuses}"


def test_rate_limit_disabled_setting_allows_unlimited_bursts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    with TestClient(app) as client:
        statuses = [client.get("/graph/methodology").status_code for _ in range(50)]
    assert all(s == 200 for s in statuses)


# ---------------------------------------------------------------------------
# WebSocket connection cap
# ---------------------------------------------------------------------------


def test_slider_connection_cap_rejects_beyond_max() -> None:
    state = SimpleNamespace(slider_connections=MAX_SLIDER_CONNECTIONS)
    assert try_reserve_slider_connection(state) is False


def test_slider_connection_cap_allows_under_max_and_releases() -> None:
    state = SimpleNamespace(slider_connections=0)
    assert try_reserve_slider_connection(state) is True
    assert state.slider_connections == 1
    release_slider_connection(state)
    assert state.slider_connections == 0


# ---------------------------------------------------------------------------
# require_api_key as a plain dependency (no app.state.settings mismatch)
# ---------------------------------------------------------------------------


def test_require_api_key_no_op_when_unconfigured() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(api_key=None))),
        headers={},
    )
    require_api_key(request)  # must not raise

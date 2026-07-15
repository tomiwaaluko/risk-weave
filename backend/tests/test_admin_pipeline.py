"""Tests for the guarded /admin/pipeline endpoints (RIS-28).

The security-critical behavior: the router is disabled unless
``RISKWEAVE_ADMIN_TOKEN`` is set, and every call requires a matching
``X-Admin-Token`` header. These gate checks run before any DB access.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from riskweave_api.main import app

_BASE_ENV = {
    "DATABASE_URL": "postgresql://riskweave:password@postgres:5432/riskweave",
    "NEO4J_URI": "bolt://neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "password",
    "REDIS_URL": "redis://redis:6379/0",
    "GEMINI_API_KEY": "test-placeholder",
}


@pytest.fixture
def client_without_token(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("RISKWEAVE_ADMIN_TOKEN", raising=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_token(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("RISKWEAVE_ADMIN_TOKEN", "s3cret-admin")
    with TestClient(app) as c:
        yield c


class TestAdminAuthGate:
    def test_disabled_returns_404_when_token_unset(self, client_without_token: TestClient) -> None:
        resp = client_without_token.post("/admin/pipeline/diagnose", params={"snapshot_id": 3})
        assert resp.status_code == 404

    def test_missing_header_is_rejected(self, client_with_token: TestClient) -> None:
        resp = client_with_token.post("/admin/pipeline/diagnose", params={"snapshot_id": 3})
        assert resp.status_code == 403

    def test_wrong_token_is_rejected(self, client_with_token: TestClient) -> None:
        resp = client_with_token.post(
            "/admin/pipeline/diagnose",
            params={"snapshot_id": 3},
            headers={"X-Admin-Token": "wrong"},
        )
        assert resp.status_code == 403

    def test_status_requires_token(self, client_with_token: TestClient) -> None:
        assert client_with_token.get("/admin/pipeline/status").status_code == 403
        ok = client_with_token.get(
            "/admin/pipeline/status", headers={"X-Admin-Token": "s3cret-admin"}
        )
        assert ok.status_code == 200
        assert ok.json()["running"] is False

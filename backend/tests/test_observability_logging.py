"""Structured JSON logging: format, request id, and secret scrubbing (RIS-33)."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from riskweave_api.main import app
from riskweave_api.observability.logging_config import JsonFormatter, scrub_secrets

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
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _make_record(msg: str, **fields: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="riskweave_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    if fields:
        record.fields = fields
    return record


class TestJsonFormatter:
    def test_emits_valid_json_with_required_fields(self) -> None:
        record = _make_record("hello world")
        payload = json.loads(JsonFormatter().format(record))
        assert payload["message"] == "hello world"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "riskweave_api.test"
        assert "timestamp" in payload

    def test_includes_extra_fields(self) -> None:
        record = _make_record("request", method="GET", path="/health", status=200, duration_ms=1.2)
        payload = json.loads(JsonFormatter().format(record))
        assert payload["method"] == "GET"
        assert payload["path"] == "/health"
        assert payload["status"] == 200
        assert payload["duration_ms"] == 1.2

    def test_redacts_named_secret_fields(self) -> None:
        record = _make_record(
            "connected", api_key="sk-live-abc123", database_url="postgres://u:p@h/db"
        )
        payload = json.loads(JsonFormatter().format(record))
        assert payload["api_key"] == "[REDACTED]"
        assert payload["database_url"] == "[REDACTED]"

    def test_redacts_bearer_token_in_message(self) -> None:
        record = _make_record("unauthorized request: Authorization: Bearer sk-abcdef123456")
        payload = json.loads(JsonFormatter().format(record))
        assert "sk-abcdef123456" not in payload["message"]
        assert "[REDACTED]" in payload["message"]


class TestScrubSecrets:
    def test_redacts_password_in_connection_url(self) -> None:
        scrubbed = scrub_secrets("postgresql://riskweave:hunter2@postgres:5432/riskweave")
        assert "hunter2" not in scrubbed
        assert "riskweave:[REDACTED]@postgres" in scrubbed

    def test_redacts_key_value_secret(self) -> None:
        scrubbed = scrub_secrets('gemini_api_key="AIzaSyD-not-a-real-key"')
        assert "AIzaSyD-not-a-real-key" not in scrubbed

    def test_leaves_non_secret_text_untouched(self) -> None:
        text = "scenario cre-2026-demo transitioned READY -> RUNNING"
        assert scrub_secrets(text) == text


class TestRequestLoggingMiddleware:
    def test_adds_request_id_header(self, client: TestClient) -> None:
        response = client.get("/health")
        assert "x-request-id" in response.headers

    def test_honors_incoming_request_id(self, client: TestClient) -> None:
        response = client.get("/health", headers={"X-Request-Id": "test-req-123"})
        assert response.headers["x-request-id"] == "test-req-123"

    def test_logs_method_path_status_duration(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="riskweave_api.request"):
            client.get("/health")
        records = [r for r in caplog.records if r.name == "riskweave_api.request"]
        assert records, "expected a structured request log line"
        fields = records[-1].fields
        assert fields["method"] == "GET"
        assert fields["path"] == "/health"
        assert fields["status"] == 200
        assert isinstance(fields["duration_ms"], float)
        assert "request_id" in fields

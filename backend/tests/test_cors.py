"""The CORS allowlist admits the real Vercel origins and rejects strangers.

RIS-41: the previous default regex expected ``riskweave`` (no hyphen) and so
matched none of the live ``risk-weave-*.vercel.app`` origins, leaving the
production frontend unable to call the backend from the browser. These tests pin
the default to the real origins and guard against a foreign site slipping in.
"""

from __future__ import annotations

import re
from pathlib import Path

from starlette.testclient import TestClient

from riskweave_api.main import app
from riskweave_api.settings import Settings

DEFAULT_REGEX = Settings.model_fields["cors_allow_origin_regex"].default

# Real Vercel production + alias origins for this project (from the Vercel
# dashboard): the stable production alias, the team production URL, and the
# git/preview subdomain shapes.
ALLOWED_ORIGINS = [
    "https://risk-weave-five.vercel.app",
    "https://risk-weave-tomiwaalukos-projects.vercel.app",
    "https://risk-weave-git-main-tomiwaalukos-projects.vercel.app",
    "https://risk-weave-7oar5kwgn-tomiwaalukos-projects.vercel.app",
    "http://localhost:3000",
]

REJECTED_ORIGINS = [
    "https://riskweave.vercel.app",  # the old (wrong) spelling must not be required
    "https://evil.com",
    "https://risk-weave-five.vercel.app.evil.com",  # suffix smuggling
    "http://risk-weave-five.vercel.app",  # http (non-local) is not allowed
    "https://risk-weave-five.vercel.app/",  # trailing slash is not an origin
]


def test_default_regex_matches_real_vercel_and_local_origins() -> None:
    for origin in ALLOWED_ORIGINS:
        assert re.match(DEFAULT_REGEX, origin), f"CORS default should allow {origin}"


def test_default_regex_rejects_foreign_and_malformed_origins() -> None:
    for origin in REJECTED_ORIGINS:
        assert not re.match(DEFAULT_REGEX, origin), f"CORS default must reject {origin}"


def test_env_example_cors_regex_matches_settings_default() -> None:
    """`.env.example` and the code default must not drift apart."""
    env_example = Path(__file__).parents[2] / ".env.example"
    line = next(
        raw
        for raw in env_example.read_text().splitlines()
        if raw.startswith("CORS_ALLOW_ORIGIN_REGEX=")
    )
    example_value = line.split("=", 1)[1]
    assert example_value == DEFAULT_REGEX


def test_preflight_returns_allow_origin_for_real_vercel_origin(monkeypatch) -> None:
    """A CORS preflight from the real production origin is granted."""
    monkeypatch.delenv("CORS_ALLOW_ORIGIN_REGEX", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://riskweave:password@postgres:5432/riskweave")
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")

    origin = "https://risk-weave-five.vercel.app"
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers.get("access-control-allow-origin") == origin

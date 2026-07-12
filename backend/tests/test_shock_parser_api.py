"""API tests for the RIS-18 preset shock-parsing endpoints.

The app's ``shock_parser`` is replaced with one backed by a fake transport so
these stay hermetic (no live Gemini call) while still exercising the real
router, dependency wiring, and response schema.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from riskweave_api.extraction.shock_parser import GeminiShockParser
from riskweave_api.main import app


class FakeTransport:
    def __init__(self, *outputs: str) -> None:
        self._outputs = list(outputs)

    def create_interaction(self, **kwargs: object) -> dict[str, object]:
        return {"output_text": self._outputs.pop(0), "usage": {}}


_CRE_PAYLOAD = json.dumps(
    {
        "scenario_pack": "cre",
        "factors": [
            {
                "factor_id": "cre_property_value",
                "direction": "down",
                "magnitude": 20,
                "unit": "percent",
                "horizon": "six quarters",
                "geography": "United States",
                "sector_scope": "cre",
                "source_quote": "Commercial real-estate values fall 20%",
            }
        ],
    }
)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with TestClient(app, raise_server_exceptions=True) as c:
        c.app.state.redis = None
        yield c


def _use_transport(client, *outputs: str) -> None:
    client.app.state.shock_parser = GeminiShockParser(FakeTransport(*outputs))


def test_presets_endpoint_lists_clickable_prompts(client):
    resp = client.get("/scenarios/presets")

    assert resp.status_code == 200
    presets = resp.json()
    assert {p["preset_id"] for p in presets} == {"cre", "oil"}
    assert all(p["prompt_text"] for p in presets)


def test_parse_preset_returns_gemini_sourced_ready_scenario(client):
    _use_transport(client, _CRE_PAYLOAD)

    resp = client.post("/scenarios/presets/cre/parse")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "gemini"
    assert payload["scenario"]["status"] == "READY"
    assert payload["scenario"]["factors"][0]["factor_id"] == "cre_property_value"
    assert payload["scenario"]["factors"][0]["magnitude"] == 20


def test_parse_preset_falls_back_without_white_screen(client):
    _use_transport(client, "garbage", "still garbage")

    resp = client.post("/scenarios/presets/cre/parse")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "fallback"
    assert payload["fallback_reason"]
    assert payload["scenario"]["status"] == "READY"


def test_parse_unknown_preset_returns_404(client):
    resp = client.post("/scenarios/presets/does-not-exist/parse")
    assert resp.status_code == 404


def test_run_accepts_parsed_preset_scenario(client):
    """The parsed READY scenario hands off to the propagation/run gate."""
    _use_transport(client, _CRE_PAYLOAD)
    scenario = client.post("/scenarios/presets/cre/parse").json()["scenario"]

    resp = client.post("/scenarios/review/run", json=scenario)

    assert resp.status_code == 200
    assert resp.json()["accepted"] is True

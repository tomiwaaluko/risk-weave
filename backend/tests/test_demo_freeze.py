"""RIS-22 reduced fixture demo freeze checks."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from riskweave_api.main import app

_ROOT = Path(__file__).resolve().parents[2]
_BUNDLE_PATH = _ROOT / "docs" / "demo" / "FROZEN_DEMO_BUNDLE.json"

_ENV = {
    "DATABASE_URL": "postgresql://riskweave:password@postgres:5432/riskweave",
    "NEO4J_URI": "bolt://neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "password",
    "REDIS_URL": "redis://redis:6379/0",
    "GEMINI_API_KEY": "test-placeholder",
}


def _bundle() -> dict[str, object]:
    return json.loads(_BUNDLE_PATH.read_text(encoding="utf-8"))


def test_frozen_demo_bundle_pins_fixture_replay_metadata() -> None:
    bundle = _bundle()

    assert bundle["snapshot_id"] == "cre-demo-2026-07-11"
    assert bundle["graph_version"] == "1.0.0"
    assert bundle["engine_version"] == "adr-001-simple-path-v1"
    assert bundle["prompt_version"] == "shock-parse-v1"
    assert bundle["seed"] == 20260711
    assert bundle["replay_label"] == "Replay mode: precomputed results from frozen bundle"

    scenarios = bundle["scenarios"]
    assert isinstance(scenarios, list)
    assert {scenario["id"] for scenario in scenarios} == {"cre-refinancing-shock"}
    for scenario in scenarios:
        assert scenario["fallback_ready"] is True
        assert scenario["surprising_path"].count("->") >= 2
        assert scenario["low_confidence_example"]


def test_fixture_replay_seed_reproduces_identical_results(monkeypatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)

    with TestClient(app) as client:
        first_seed = client.post("/graph/seed").json()
        first_run = client.post("/registry/run_scenario/cre-demo", json={"severity": 1.0}).json()
        second_seed = client.post("/graph/seed").json()
        second_run = client.post("/registry/run_scenario/cre-demo", json={"severity": 1.0}).json()

    assert first_seed["snapshot_id"] == "cre-demo-2026-07-11"
    assert first_seed["graph_version"] == "1.0.0"
    assert first_seed["checksum"] == second_seed["checksum"]
    assert first_seed["factors"] == second_seed["factors"]
    first_result = {k: v for k, v in first_run["result"].items() if k != "latency_ms"}
    second_result = {k: v for k, v in second_run["result"].items() if k != "latency_ms"}
    assert first_result == second_result

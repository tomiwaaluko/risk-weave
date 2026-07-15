"""Tests for the live-graph endpoint POST /graph/live (RIS-28).

Asserts that the endpoint serves a graph assembled from real extraction output
(not ``load_graph_fixture()``), that every generated edge carries full Graft 2
provenance, that the scenario is immediately runnable (slider round-trip), and
that the fixture remains the explicit fallback when the live artifact is absent.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from riskweave.entity_resolution import Resolver
from riskweave.graph.assembly import load_universe
from riskweave.graph.live import ExtractedRelationship, build_live_graph, graph_to_artifact
from riskweave_api.main import app

_ENV = {
    "DATABASE_URL": "postgresql://riskweave:password@postgres:5432/riskweave",
    "NEO4J_URI": "bolt://neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "password",
    "REDIS_URL": "redis://redis:6379/0",
    "GEMINI_API_KEY": "test-placeholder",
}

_UNIVERSE = {
    "entities": [
        {
            "id": "sector:office",
            "canonical_name": "US Office CRE",
            "entity_type": "sector",
            "packs": ["cre"],
            "aliases": ["office cre"],
        },
        {
            "id": "reit:bxp",
            "canonical_name": "Boston Properties",
            "entity_type": "reit",
            "packs": ["cre"],
            "ticker": "BXP",
        },
        {
            "id": "bank:wfc",
            "canonical_name": "Wells Fargo",
            "entity_type": "bank",
            "packs": ["cre"],
            "ticker": "WFC",
        },
    ]
}


def _rel(
    source: str, target: str, magnitude: str, passage: str, start: int
) -> ExtractedRelationship:
    return ExtractedRelationship(
        source_entity=source,
        target_entity=target,
        relationship_type="creditor",
        direction="positive",
        disclosed_magnitude=magnitude,
        source_passage=passage,
        source_document_id="0000038777-24-000012",
        char_start=start,
        char_end=start + len(passage),
        extraction_confidence=0.9,
        filing_date=date(2024, 2, 27),
        data_timestamp=datetime(2023, 12, 31),
    )


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def live_artifact(tmp_path: Path) -> Path:
    universe_path = tmp_path / "entities.json"
    universe_path.write_text(json.dumps(_UNIVERSE), encoding="utf-8")
    resolver = Resolver.from_universe_file(universe_path)
    entities = load_universe(str(universe_path))
    relationships = [
        _rel("WFC", "BXP", "approximately 28% of the loan portfolio", "approximately 28%", 100),
        _rel("office cre", "BXP", "roughly 90% of revenue", "roughly 90% of revenue", 500),
    ]
    result = build_live_graph(
        relationships, resolver, entities, snapshot_id="snapshot-3", graph_version="live-1.0.0"
    )
    artifact = graph_to_artifact(result, note="test live graph")
    path = tmp_path / "live_graph.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestGraphLive:
    def test_live_returns_assembled_graph(
        self, client: TestClient, live_artifact: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RISKWEAVE_LIVE_GRAPH_PATH", str(live_artifact))
        resp = client.post("/graph/live")
        assert resp.status_code == 201
        data = resp.json()
        assert data["scenario_id"] == "cre-live"
        assert data["snapshot_id"] == "snapshot-3"
        assert data["state"] == "READY"
        assert len(data["edges"]) == 2

    def test_every_live_edge_has_complete_provenance(
        self, client: TestClient, live_artifact: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RISKWEAVE_LIVE_GRAPH_PATH", str(live_artifact))
        data = client.post("/graph/live").json()
        for edge in data["edges"]:
            prov = edge["provenance"]
            assert prov["source_document_id"].strip()
            assert prov["source_passage"].strip()
            assert prov["char_end"] - prov["char_start"] == len(prov["source_passage"])
            assert edge["method_id"] == "DER-CONCENTRATION"
            assert edge["method_name"].strip()

    def test_live_scenario_is_runnable(
        self, client: TestClient, live_artifact: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # RIS-28 acceptance: scenario run + slider round-trip against the live graph.
        monkeypatch.setenv("RISKWEAVE_LIVE_GRAPH_PATH", str(live_artifact))
        client.post("/graph/live")
        resp = client.post("/registry/run_scenario/cre-live", json={"severity": 0.8})
        assert resp.status_code == 200
        assert resp.json()["result"]["impacts"], "propagation produced no impacts"

    def test_live_is_idempotent(
        self, client: TestClient, live_artifact: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RISKWEAVE_LIVE_GRAPH_PATH", str(live_artifact))
        r1 = client.post("/graph/live")
        r2 = client.post("/graph/live")
        assert r1.json()["checksum"] == r2.json()["checksum"]

    def test_missing_artifact_returns_503_and_fixture_still_works(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RISKWEAVE_LIVE_GRAPH_PATH", str(tmp_path / "does-not-exist.json"))
        resp = client.post("/graph/live")
        assert resp.status_code == 503
        assert "build_live" in resp.json()["detail"]
        # The curated fixture remains available as the explicit fallback.
        assert client.post("/graph/seed").status_code == 201

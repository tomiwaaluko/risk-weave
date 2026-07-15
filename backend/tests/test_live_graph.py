"""Tests for the live-graph builder (RIS-28).

The defining acceptance criterion: every edge in the *generated* live graph —
not just the hand-authored fixture — carries full Graft 2 provenance
(`RW-ALG-032`). These tests exercise the resolution -> derivation -> assembly
pipeline over representative extraction rows and assert that invariant, plus
determinism, honest dropping (no fabricated edges), and artifact round-trip.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from riskweave.derivations.registry import get_method
from riskweave.entity_resolution import Resolver
from riskweave.graph import load_graph_fixture
from riskweave.graph.assembly import load_universe
from riskweave.graph.live import ExtractedRelationship, build_live_graph, graph_to_artifact

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
            "cik": "0000038777",
        },
        {
            "id": "bank:wfc",
            "canonical_name": "Wells Fargo",
            "entity_type": "bank",
            "packs": ["cre"],
            "ticker": "WFC",
            "cik": "0000072971",
        },
        {
            "id": "reit:vno",
            "canonical_name": "Vornado",
            "entity_type": "reit",
            "packs": ["cre"],
            "ticker": "VNO",
        },
    ]
}


def _rel(
    source: str,
    target: str,
    rel_type: str,
    magnitude: str | None,
    passage: str,
    *,
    char_start: int = 100,
    confidence: float = 0.9,
) -> ExtractedRelationship:
    return ExtractedRelationship(
        source_entity=source,
        target_entity=target,
        relationship_type=rel_type,
        direction="positive",
        disclosed_magnitude=magnitude,
        source_passage=passage,
        source_document_id="0000038777-24-000012",
        char_start=char_start,
        char_end=char_start + len(passage),
        extraction_confidence=confidence,
        filing_date=date(2024, 2, 27),
        data_timestamp=datetime(2023, 12, 31),
    )


_RELATIONSHIPS = [
    _rel(
        "WFC",
        "BXP",
        "creditor",
        "approximately 28% of the loan portfolio",
        "approximately 28% of our commercial real estate loan portfolio",
        char_start=100,
    ),
    _rel(
        "office cre",
        "BXP",
        "sector_exposure",
        "roughly 90% of revenue",
        "office properties represented roughly 90% of our total revenues",
        char_start=500,
    ),
    # No disclosed magnitude -> no number -> no edge (no fabricated weights).
    _rel("WFC", "VNO", "creditor", None, "we also lend to Vornado", char_start=900),
    # Unresolvable target -> dropped, never guessed into the universe.
    _rel("WFC", "Unknown Holdings LLC", "creditor", "10% loans", "10% loans", char_start=1200),
    # Self-loop after resolution (BXP == Boston Properties) -> dropped.
    _rel("BXP", "Boston Properties", "creditor", "5% of loans", "5% of loans", char_start=1500),
]


@pytest.fixture
def universe_file(tmp_path: Path) -> Path:
    path = tmp_path / "entities.json"
    path.write_text(json.dumps(_UNIVERSE), encoding="utf-8")
    return path


@pytest.fixture
def result(universe_file: Path):
    resolver = Resolver.from_universe_file(universe_file)
    entities = load_universe(str(universe_file))
    return build_live_graph(
        _RELATIONSHIPS,
        resolver,
        entities,
        snapshot_id="snapshot-3",
        graph_version="live-1.0.0",
    )


class TestLiveBuild:
    def test_builds_edges_only_for_resolvable_provenanced_relationships(self, result) -> None:
        assert result.report.relationships_seen == 5
        assert result.report.edges_built == 2
        assert len(result.graph.edges) == 2

    def test_every_generated_edge_carries_full_provenance(self, result) -> None:
        # RW-ALG-032: no edge without provenance — holds for GENERATED edges,
        # verified by an automated test (RIS-28 acceptance criterion).
        assert result.graph.provenance_coverage() == 1.0
        for edge in result.graph.edges:
            prov = edge.record.provenance
            assert prov.source_document_id.strip()
            assert prov.source_passage.strip()
            assert prov.char_end - prov.char_start == len(prov.source_passage)
            assert 0.0 <= prov.extraction_confidence <= 1.0
            assert edge.record.data_timestamps
            # Weight came from a registered deterministic method (RW-ALG-001/004).
            assert get_method(edge.record.method_id).method_id == "DER-CONCENTRATION"

    def test_edges_use_resolved_canonical_ids_not_raw_mentions(self, result) -> None:
        endpoints = {e.source_id for e in result.graph.edges} | {
            e.target_id for e in result.graph.edges
        }
        assert endpoints <= {"sector:office", "reit:bxp", "bank:wfc"}
        assert "WFC" not in endpoints and "BXP" not in endpoints

    def test_drops_are_recorded_with_reasons(self, result) -> None:
        reasons = result.report.drops_by_reason
        assert reasons.get("no_disclosed_magnitude") == 1
        assert reasons.get("unresolved_endpoint") == 1
        assert reasons.get("self_loop") == 1

    def test_disclosed_magnitude_becomes_the_edge_weight(self, result) -> None:
        by_pair = {(e.source_id, e.target_id): e for e in result.graph.edges}
        assert by_pair[("bank:wfc", "reit:bxp")].record.value == pytest.approx(0.28)
        assert by_pair[("sector:office", "reit:bxp")].record.value == pytest.approx(0.90)

    def test_build_is_deterministic(self, universe_file: Path) -> None:
        resolver = Resolver.from_universe_file(universe_file)
        entities = load_universe(str(universe_file))
        first = build_live_graph(
            _RELATIONSHIPS, resolver, entities, snapshot_id="snapshot-3", graph_version="v1"
        )
        second = build_live_graph(
            list(reversed(_RELATIONSHIPS)),
            resolver,
            entities,
            snapshot_id="snapshot-3",
            graph_version="v1",
        )
        assert first.graph.checksum == second.graph.checksum

    def test_default_factors_are_runnable_and_prefer_sector(self, result) -> None:
        factors = result.default_factors
        assert factors, "expected at least one default seed factor"
        endpoints = {e.source_id for e in result.graph.edges} | {
            e.target_id for e in result.graph.edges
        }
        for _fid, node_id, _mag in factors:
            assert node_id in endpoints
        # The sector origin is the preferred shock entry point.
        assert factors[0][1] == "sector:office"


class TestArtifactRoundTrip:
    def test_artifact_reloads_to_the_same_checksum(self, result, tmp_path: Path) -> None:
        artifact = graph_to_artifact(result, note="test")
        path = tmp_path / "graph.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        reloaded = load_graph_fixture(path)
        assert reloaded.checksum == result.graph.checksum

    def test_artifact_carries_factors_and_report(self, result) -> None:
        artifact = graph_to_artifact(result, note="test")
        assert artifact["factors"], "artifact must carry runnable seed factors"
        assert artifact["report"]["edges_built"] == 2
        assert artifact["report"]["entity_coverage"] == 3


class TestEvaluationBridge:
    def test_extraction_metrics_score_real_assembled_output(self, result) -> None:
        # RIS-28 acceptance: the evaluation metrics score REAL live output, not a
        # fixture. Predicted keys come from the assembled live graph.
        from riskweave.evaluation import extraction_keys_from_graph, extraction_metrics

        predicted = extraction_keys_from_graph(result.graph)
        assert ("bank:wfc", "reit:bxp", "creditor") in predicted
        gold = [
            ("bank:wfc", "reit:bxp", "creditor"),
            ("sector:office", "reit:bxp", "sector_exposure"),
        ]
        metrics = extraction_metrics(predicted, gold)
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0

    def test_method_distribution_over_live_edges(self, result) -> None:
        from riskweave.evaluation import method_distribution

        assert method_distribution(result.graph) == {"DER-CONCENTRATION": 2}

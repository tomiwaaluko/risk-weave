"""Closed §13.2 tool-registry tests (RIS-19, `RW-AI-002`, `RW-SEC-002`).

The registry is the server-side trust boundary: only the ten §13.2 tools exist,
their arguments are validated against a closed schema, and the breach-distance
and duration tools are wired to the shipped Graft 1/3 code. Nothing here calls a
model — every result is deterministic arithmetic over approved run state.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from riskweave.breach.distance import CovenantKind, CovenantThreshold
from riskweave.derivations.provenance import Provenance
from riskweave.explain import (
    TOOL_NAMES,
    EdgeEvidence,
    RunToolContext,
    SecurityTerms,
    ToolArgumentError,
    UnknownToolError,
    build_registry,
)
from riskweave.propagation import (
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)

_SPEC_13_2 = {
    "resolve_entity",
    "get_company_exposures",
    "run_scenario",
    "propagate_shock",
    "get_propagation_paths",
    "calculate_breach_distance",
    "calculate_duration",
    "get_ratio",
    "retrieve_filing_passage",
    "retrieve_fred_series",
}


def _context(**overrides: object) -> RunToolContext:
    snapshot = GraphSnapshot(
        snapshot_id="s",
        graph_version="1.0.0",
        nodes=(
            GraphNode(node_id="a", node_type="sector", name="Office CRE"),
            GraphNode(node_id="b", node_type="reit", name="Boston Properties"),
        ),
        edges=(
            GraphEdge(
                edge_id="e1",
                source_id="a",
                target_id="b",
                weight=0.5,
                method_id="DER-CONCENTRATION",
                provenance_ref="doc-1#10-30",
            ),
        ),
    )
    result = propagate(
        snapshot,
        Scenario(scenario_id="scn", factors=(ShockFactor("office", "a", 1.0),)),
    )
    provenance = {
        "e1": EdgeEvidence(
            citation_id="",
            edge_id="e1",
            source_name="a",
            target_name="b",
            relationship_type="sector_exposure",
            method_id="DER-CONCENTRATION",
            source_document_id="doc-1",
            source_passage="Office concentration.",
            char_start=10,
            char_end=31,
            filing_date="2024-02-27",
            data_timestamp="2023-12-31T00:00:00",
            extraction_confidence=0.9,
        )
    }
    kwargs: dict[str, object] = {
        "scenario_id": "scn",
        "result": result,
        "snapshot": snapshot,
        "provenance_by_edge": provenance,
        "node_names": {"a": "Office CRE", "b": "Boston Properties"},
        "node_types": {"a": "sector", "b": "reit"},
    }
    kwargs.update(overrides)
    return RunToolContext(**kwargs)  # type: ignore[arg-type]


def test_registry_exposes_exactly_the_13_2_tools() -> None:
    assert TOOL_NAMES == _SPEC_13_2
    registry = build_registry(_context())
    assert {d["name"] for d in registry.declarations()} == _SPEC_13_2


def test_unknown_tool_is_refused_server_side() -> None:
    registry = build_registry(_context())
    with pytest.raises(UnknownToolError):
        registry.invoke("exec_shell", {"cmd": "rm -rf /"})


def test_unexpected_argument_is_rejected() -> None:
    registry = build_registry(_context())
    with pytest.raises(ToolArgumentError):
        registry.invoke("resolve_entity", {"name": "x", "injection": "y"})


def test_missing_required_argument_is_rejected() -> None:
    registry = build_registry(_context())
    with pytest.raises(ToolArgumentError):
        registry.invoke("get_company_exposures", {})


def test_wrong_argument_type_is_rejected() -> None:
    registry = build_registry(_context())
    with pytest.raises(ToolArgumentError):
        registry.invoke("resolve_entity", {"name": 123})


def test_exposures_returns_weights_and_resolvable_citations() -> None:
    registry = build_registry(_context())
    result = registry.invoke("get_company_exposures", {"entity_id": "a"})
    assert result.payload["outgoing_edges"][0]["weight"] == 0.5
    assert 0.5 in result.numbers
    assert [c.citation_id for c in result.citations] == ["cit-e1"]


def test_propagation_paths_number_set_covers_contributions() -> None:
    registry = build_registry(_context())
    result = registry.invoke("get_propagation_paths", {"entity_id": "b"})
    impact_paths = result.payload["paths"]
    assert impact_paths
    assert result.payload["paths"][0]["citation_ids"] == ["cit-e1"]
    # Every contribution figure the tool reports is in the approved number set.
    for path in impact_paths:
        assert path["contribution"] in result.numbers


def _leverage_threshold() -> CovenantThreshold:
    provenance = Provenance(
        source_document_id="doc-cov",
        filing_date=date(2024, 2, 27),
        source_passage="Leverage shall not exceed 4.50x.",
        char_start=0,
        char_end=len("Leverage shall not exceed 4.50x."),
        data_timestamp=datetime(2023, 12, 31),
        extraction_confidence=0.95,
    )
    return CovenantThreshold(
        entity_id="b",
        kind=CovenantKind.LEVERAGE,
        value=4.5,
        provenance=provenance,
    )


def test_breach_distance_is_wired_to_graft1_and_withholds_without_data() -> None:
    # Without a threshold on file, the tool returns "no data" rather than a number.
    empty = build_registry(_context())
    absent = empty.invoke("calculate_breach_distance", {"entity_id": "b"})
    assert absent.payload["available"] is False
    assert absent.numbers == ()

    # With a threshold, it computes a real breach distance via the shipped Graft 1 code.
    registry = build_registry(_context(covenant_thresholds={"b": (_leverage_threshold(), 4.2)}))
    result = registry.invoke("calculate_breach_distance", {"entity_id": "b"})
    assert result.payload["available"] is True
    assert result.payload["threshold_value"] == 4.5
    assert result.payload["current_value"] == 4.2
    assert 4.5 in result.numbers and 4.2 in result.numbers
    assert result.citations and result.citations[0].source_document_id == "doc-cov"


def test_duration_is_wired_to_graft3_and_withholds_without_data() -> None:
    absent = build_registry(_context()).invoke("calculate_duration", {"security_id": "bond-x"})
    assert absent.payload["available"] is False

    terms = SecurityTerms(coupon_rate=0.05, yield_rate=0.05, years_to_maturity=10.0)
    registry = build_registry(_context(securities={"bond-x": terms}))
    result = registry.invoke("calculate_duration", {"security_id": "bond-x"})
    assert result.payload["available"] is True
    assert result.payload["modified_duration"] > 0
    assert result.numbers[0] == result.payload["modified_duration"]


def test_tool_numbers_never_include_model_supplied_arguments() -> None:
    # propagate_shock takes a `magnitude` argument; it must not leak into the
    # approved number set (that would launder a fabricated figure past the guard).
    registry = build_registry(_context())
    result = registry.invoke("propagate_shock", {"factor_id": "office", "magnitude": 999.0})
    assert 999.0 not in result.numbers

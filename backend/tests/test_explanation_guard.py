"""Explanation-guard tests (RIS-19, `RW-AI-011`, `RW-FR-023`).

Asserts the invariant tests must assert: every numeric token in a generated
explanation exists in the computation payload; anything else is rejected.
"""

import pytest

from riskweave.explain import (
    ExplanationPayload,
    extract_numeric_tokens,
    guard_explanation,
    payload_for_node,
)
from riskweave.propagation import (
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)


# --------------------------------------------------------------------------- #
# Token extraction                                                             #
# --------------------------------------------------------------------------- #
def test_extracts_varied_number_formats():
    text = "Leverage rose to 4.8x from 4.2x; exposure $1,200 (down 3%), score 87."
    tokens = extract_numeric_tokens(text)
    assert "4.8" in tokens
    assert "4.2" in tokens
    assert "$1,200" in tokens
    assert "3" in tokens
    assert "87" in tokens


def test_ignores_non_numeric_text():
    assert extract_numeric_tokens("no numbers here at all") == ()


# --------------------------------------------------------------------------- #
# The core invariant                                                           #
# --------------------------------------------------------------------------- #
def test_accepts_explanation_with_only_payload_numbers():
    payload = ExplanationPayload.from_values(4.2, 4.8, 4.5)
    text = "Leverage moves from 4.2x today to 4.8x, past the 4.5x covenant."
    assert guard_explanation(text, payload).ok


def test_rejects_hallucinated_number():
    payload = ExplanationPayload.from_values(4.2, 4.8, 4.5)
    text = "Leverage moves from 4.2x to 4.8x, and default risk is 73%."
    result = guard_explanation(text, payload)
    assert not result.ok
    assert "73" in result.unsupported


def test_rounding_to_display_precision_is_allowed():
    # Payload has the full-precision score; prose rounds it.
    payload = ExplanationPayload.from_values(86.7421)
    assert guard_explanation("The risk score is 86.7.", payload).ok
    assert guard_explanation("The risk score is 87.", payload).ok


def test_close_but_wrong_number_is_rejected():
    payload = ExplanationPayload.from_values(86.7421)
    # 91 is not a rounding of 86.74 at any displayed precision.
    assert not guard_explanation("The risk score is 91.", payload).ok


def test_negative_accounting_format():
    payload = ExplanationPayload.from_values(-3.2)
    assert guard_explanation("Net change was (3.2).", payload).ok


def test_zero_handled():
    payload = ExplanationPayload.from_values(0.0, 12.0)
    assert guard_explanation("Contribution was 0 across 12 paths.", payload).ok
    assert not guard_explanation("Contribution was 5.", payload).ok


# --------------------------------------------------------------------------- #
# Payload built from a real propagation result                                 #
# --------------------------------------------------------------------------- #
def build_result():
    snap = GraphSnapshot(
        snapshot_id="s",
        graph_version="1.0.0",
        nodes=(
            GraphNode(node_id="a", node_type="company", name="A"),
            GraphNode(node_id="b", node_type="company", name="B"),
        ),
        edges=(
            GraphEdge(
                edge_id="e1",
                source_id="a",
                target_id="b",
                weight=0.5,
                method_id="DER-CREDIT",
                provenance_ref="p",
            ),
        ),
    )
    return propagate(
        snap,
        Scenario(
            scenario_id="scn", factors=(ShockFactor(factor_id="f", node_id="a", magnitude=1.0),)
        ),
    )


def test_payload_for_node_permits_its_own_numbers():
    result = build_result()
    payload = payload_for_node(result, "b")
    score = result.impacts["b"].risk_score
    # An explanation citing the node's own computed score passes.
    assert guard_explanation(f"Node B scores {score:.1f}.", payload).ok


def test_payload_for_node_rejects_foreign_number():
    result = build_result()
    payload = payload_for_node(result, "b")
    assert not guard_explanation("Node B scores 99.9 with a 250 bp move.", payload).ok


def test_payload_rejects_bool():
    with pytest.raises(TypeError):
        ExplanationPayload(numbers=(True,))

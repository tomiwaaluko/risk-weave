"""Evidence-bound explanation generation tests (RIS-19, `RW-AI-011`).

The defining invariant: the prose Gemini writes is only ever surfaced when every
numeric token in it exists in the computation payload. These tests drive the
generation orchestration with a fake transport (no network, no key) and assert:

* generated prose passes the numeric-containment guard (0 violations — the
  release metric, ``test_explanation_numbers_all_in_payload``),
* an unbacked number triggers exactly one regeneration and then the labeled
  structured-numbers fallback, never the offending prose, and
* citation ids in accepted prose resolve to real provenance records.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from riskweave.explain import (
    Audience,
    EdgeEvidence,
    build_node_context,
    generate_node_explanation,
    guard_explanation,
    strip_citation_markers,
)
from riskweave.propagation import (
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)


class FakeTransport:
    """Returns queued JSON replies; repeats the last once the queue is drained."""

    def __init__(self, responses: list[dict[str, object]]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def create_interaction(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return {"output_text": json.dumps(self._responses[index])}


def _build_result():
    snap = GraphSnapshot(
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
                provenance_ref="0000038777-24-000012#41250-41360",
            ),
        ),
    )
    return propagate(
        snap,
        Scenario(
            scenario_id="scn",
            factors=(ShockFactor(factor_id="office-shock", node_id="a", magnitude=1.0),),
        ),
    )


def _provenance() -> dict[str, EdgeEvidence]:
    return {
        "e1": EdgeEvidence(
            citation_id="",
            edge_id="e1",
            source_name="a",
            target_name="b",
            relationship_type="sector_exposure",
            method_id="DER-CONCENTRATION",
            source_document_id="0000038777-24-000012",
            source_passage="Class A office properties represented approximately 92% of revenues.",
            char_start=41250,
            char_end=41320,
            filing_date="2024-02-27",
            data_timestamp="2023-12-31T00:00:00",
            extraction_confidence=0.94,
        )
    }


def _context():
    result = _build_result()
    return build_node_context(
        result,
        "b",
        node_name="Boston Properties",
        node_type="reit",
        provenance_by_edge=_provenance(),
        node_names={"a": "Office CRE", "b": "Boston Properties"},
    )


# --------------------------------------------------------------------------- #
# The release metric                                                           #
# --------------------------------------------------------------------------- #
def test_explanation_numbers_all_in_payload() -> None:
    context, payload = _context()
    text = (
        f"Boston Properties carries a risk score of {context.risk_score:.1f} "
        f"driven by {context.path_count} transmission path from the office shock [cit-1]."
    )
    transport = FakeTransport([{"explanation": text, "citations": ["cit-1"]}])

    generated = generate_node_explanation(context, payload, transport)

    assert not generated.used_fallback
    assert generated.prose is not None
    assert generated.guard_violations == ()
    # 0 violations against the real payload — the release metric.
    guard = guard_explanation(strip_citation_markers(generated.prose), payload)
    assert guard.ok
    assert guard.unsupported == ()


@pytest.mark.parametrize("audience", [Audience.ANALYST, Audience.STUDENT, Audience.RETAIL])
def test_explanation_numbers_all_in_payload_for_every_audience(audience: Audience) -> None:
    # RW-FR-022: all three audience variants are held to the identical guard and
    # generate with 0 numeric violations (AC #1). The voice differs; the numbers
    # do not.
    context, payload = _context()
    text = (
        f"Boston Properties carries a risk score of {context.risk_score:.1f} "
        f"driven by {context.path_count} transmission path from the office shock [cit-1]."
    )
    transport = FakeTransport([{"explanation": text, "citations": ["cit-1"]}])

    generated = generate_node_explanation(context, payload, transport, audience=audience)

    assert generated.audience is audience
    assert not generated.used_fallback
    assert generated.guard_violations == ()
    guard = guard_explanation(strip_citation_markers(generated.prose), payload)
    assert guard.ok and guard.unsupported == ()
    # The audience framing reached the prompt, not the guarded numbers.
    assert audience.value in str(transport.calls[0]["input"]).lower()


def test_generation_is_a_real_transport_call() -> None:
    context, payload = _context()
    transport = FakeTransport(
        [{"explanation": "Exposed via office-sector transmission [cit-1].", "citations": ["cit-1"]}]
    )
    generate_node_explanation(context, payload, transport)
    # The prose was produced by the injected transport, not templated locally.
    assert len(transport.calls) == 1
    assert "FIGURES" in str(transport.calls[0]["input"])


# --------------------------------------------------------------------------- #
# Guard failure → regenerate once → fallback                                   #
# --------------------------------------------------------------------------- #
def test_hallucinated_number_regenerates_then_falls_back() -> None:
    context, payload = _context()
    bad = {"explanation": "Default probability is 73% [cit-1].", "citations": ["cit-1"]}
    transport = FakeTransport([bad])  # always hallucinates

    generated = generate_node_explanation(context, payload, transport)

    assert generated.used_fallback
    assert generated.prose is None  # offending prose is never surfaced
    assert generated.attempts == 2  # initial + one regeneration
    assert len(transport.calls) == 2
    assert "73" in generated.guard_violations
    # Fallback numbers are all backed by the payload.
    assert generated.structured_numbers
    for number in generated.structured_numbers:
        assert payload.permits(Decimal(str(number.value)))


def test_regeneration_can_recover() -> None:
    context, payload = _context()
    bad = {"explanation": "Default risk 73% [cit-1].", "citations": ["cit-1"]}
    good = {
        "explanation": f"Risk score {context.risk_score:.1f} from the office shock [cit-1].",
        "citations": ["cit-1"],
    }
    transport = FakeTransport([bad, good])

    generated = generate_node_explanation(context, payload, transport)

    assert not generated.used_fallback
    assert generated.attempts == 2
    assert generated.prose is not None


# --------------------------------------------------------------------------- #
# Citations                                                                    #
# --------------------------------------------------------------------------- #
def test_citation_ids_resolve_to_provenance() -> None:
    context, payload = _context()
    good = {"explanation": "Exposed through office concentration [cit-1].", "citations": ["cit-1"]}
    transport = FakeTransport([good])

    generated = generate_node_explanation(context, payload, transport)

    assert not generated.used_fallback
    assert [c.citation_id for c in generated.citations] == ["cit-1"]
    assert generated.citations[0].source_document_id == "0000038777-24-000012"
    assert "92%" in generated.citations[0].source_passage


def test_unknown_citation_is_rejected() -> None:
    context, payload = _context()
    # cit-9 does not exist; even with clean numbers this must not be surfaced.
    bad = {"explanation": "Exposed through concentration [cit-9].", "citations": ["cit-9"]}
    transport = FakeTransport([bad])

    generated = generate_node_explanation(context, payload, transport)

    assert generated.used_fallback
    assert "cit-9" in generated.guard_violations


def test_citation_marker_digits_are_not_flagged() -> None:
    # The '1' inside [cit-1] must be stripped before the numeric guard runs.
    assert strip_citation_markers("Score is high [cit-1].") == "Score is high ."


def test_context_assigns_citations_and_augments_payload() -> None:
    context, payload = _context()
    assert [e.citation_id for e in context.evidence] == ["cit-1"]
    assert context.paths[0].citation_ids == ("cit-1",)
    # The presented path count is a permitted figure.
    assert payload.permits(Decimal(str(context.path_count)))

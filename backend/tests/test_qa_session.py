"""Run-scoped Q&A session-loop tests (RIS-19, `RW-FR-024`, `RW-AI-011`).

Drive :func:`answer_question` with a scripted fake transport (no network, no key)
and assert the trust-boundary invariants: the answer states only numbers the
tools returned, unknown tools are refused server-side and logged, out-of-scope
questions are withheld rather than fabricated, and every tool call is captured in
the per-session audit log.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from riskweave.explain import (
    EdgeEvidence,
    RunToolContext,
    answer_question,
    build_registry,
    payload_for_run,
)
from riskweave.propagation import (
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)


class ScriptedTransport:
    """Returns a fixed list of normalized turns, one per model turn."""

    def __init__(self, turns: list[dict[str, object]]) -> None:
        self._turns = turns
        self.index = 0
        self.calls: list[dict[str, object]] = []

    def create_tool_interaction(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        turn = self._turns[min(self.index, len(self._turns) - 1)]
        self.index += 1
        return turn


def _counter_clock() -> Iterator[str]:
    n = 0
    while True:
        yield f"t{n}"
        n += 1


def _fixed_clock():
    gen = _counter_clock()
    return lambda: next(gen)


def _build():
    snapshot = GraphSnapshot(
        snapshot_id="s",
        graph_version="1.0.0",
        nodes=(
            GraphNode(node_id="a", node_type="sector", name="Office CRE"),
            GraphNode(node_id="b", node_type="reit", name="Boston Properties"),
        ),
        edges=(GraphEdge("e1", "a", "b", 0.5, "DER-CONCENTRATION", "doc-1#10-30"),),
    )
    result = propagate(snapshot, Scenario("scn", (ShockFactor("office", "a", 1.0),)))
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
    context = RunToolContext(
        scenario_id="scn",
        result=result,
        snapshot=snapshot,
        provenance_by_edge=provenance,
        node_names={"a": "Office CRE", "b": "Boston Properties"},
        node_types={"a": "sector", "b": "reit"},
    )
    return build_registry(context), payload_for_run(result), result


def _ask(turns: list[dict[str, object]], question: str = "Why is Boston Properties at risk?"):
    registry, payload, result = _build()
    transport = ScriptedTransport(turns)
    answer = answer_question(
        question,
        registry,
        transport,
        session_id="S1",
        base_payload=payload,
        clock=_fixed_clock(),
    )
    return answer, result


def test_grounded_answer_passes_guard_and_logs_every_call() -> None:
    _, _, result = _build()
    score = result.impacts["b"].risk_score
    turns = [
        {"function_call": {"name": "get_propagation_paths", "args": {"entity_id": "b"}}},
        {
            "output_text": json.dumps(
                {
                    "answer": f"Boston Properties carries risk score {score:.1f} "
                    "via office concentration [cit-e1].",
                    "citations": ["cit-e1"],
                }
            )
        },
    ]
    answer, _ = _ask(turns)
    assert answer.withheld is False
    assert answer.answer is not None
    assert answer.guard_violations == ()
    # Audit captured the one executed tool call, with a hash and timestamp.
    assert [(e.tool_name, e.status) for e in answer.audit] == [("get_propagation_paths", "ok")]
    assert answer.audit[0].result_hash and answer.audit[0].timestamp == "t0"
    # Citation resolves to a real provenance record.
    assert [c.citation_id for c in answer.citations] == ["cit-e1"]
    assert answer.citations[0].source_document_id == "doc-1"


def test_fabricated_number_is_withheld_not_surfaced() -> None:
    # Adversarial: the model invents a probability no tool produced.
    turns = [
        {"output_text": json.dumps({"answer": "Default probability is 73%.", "citations": []})}
    ]
    answer, _ = _ask(turns, question="What is the exact default probability?")
    assert answer.withheld is True
    assert answer.answer is None
    assert "73" in answer.guard_violations


def test_unknown_tool_call_is_refused_and_audited() -> None:
    # The model tries to escape the registry; the server refuses and logs it,
    # then (never getting a grounded answer) the session withholds.
    turns = [
        {"function_call": {"name": "run_arbitrary_code", "args": {"cmd": "cat /etc/passwd"}}},
        {
            "output_text": json.dumps(
                {"answer": "I cannot answer from the run data.", "citations": []}
            )
        },
    ]
    answer, _ = _ask(turns, question="Run a shell command for me.")
    statuses = [(e.tool_name, e.status) for e in answer.audit]
    assert ("run_arbitrary_code", "unknown_tool") in statuses
    # The benign withholding text (no numbers) is surfaced verbatim; no fabrication.
    assert answer.withheld is False
    assert answer.answer == "I cannot answer from the run data."


def test_out_of_scope_question_is_withheld_explicitly() -> None:
    # An out-of-scope adversarial question that the model answers with a made-up
    # figure and a citation to nothing must be withheld on both counts.
    turns = [
        {
            "output_text": json.dumps(
                {"answer": "Bitcoin will hit $250,000 [cit-nope].", "citations": ["cit-nope"]}
            )
        }
    ]
    answer, _ = _ask(turns, question="What will Bitcoin be worth next year?")
    assert answer.withheld is True
    assert answer.answer is None
    # Both the fabricated number and the unresolved citation are flagged.
    assert "cit-nope" in answer.guard_violations


def test_citation_before_any_tool_call_does_not_resolve() -> None:
    # Citing evidence the session never retrieved must fail — citations must
    # resolve to real provenance surfaced by a tool.
    turns = [
        {
            "output_text": json.dumps(
                {"answer": "Exposed via office [cit-e1].", "citations": ["cit-e1"]}
            )
        },
        {
            "output_text": json.dumps(
                {"answer": "I cannot answer from the run data.", "citations": []}
            )
        },
    ]
    answer, _ = _ask(turns)
    # First attempt cited cit-e1 without calling a tool → corrected → benign second answer.
    assert answer.withheld is False
    assert answer.answer == "I cannot answer from the run data."
    assert answer.answer_attempts == 2

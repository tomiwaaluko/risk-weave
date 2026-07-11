"""Evaluation-metrics tests (RIS-21, `RW-OPS-001`, spec §15)."""

import pytest

from riskweave.evaluation import (
    EvaluationError,
    LabeledRelationship,
    LabelError,
    citation_correctness_rate,
    entity_resolution_accuracy,
    extraction_metrics,
    latency_summary,
    scenario_stability,
    unsupported_claim_rate,
)
from riskweave.explain import ExplanationPayload


# --------------------------------------------------------------------------- #
# Extraction precision / recall / F1                                           #
# --------------------------------------------------------------------------- #
def test_extraction_metrics_hand_computed():
    gold = [("a", "b", "creditor"), ("b", "c", "supplier"), ("c", "d", "customer")]
    predicted = [("a", "b", "creditor"), ("b", "c", "supplier"), ("x", "y", "supplier")]
    m = extraction_metrics(predicted, gold)
    assert (m.true_positives, m.false_positives, m.false_negatives) == (2, 1, 1)
    assert m.precision == pytest.approx(2 / 3)
    assert m.recall == pytest.approx(2 / 3)
    assert m.f1 == pytest.approx(2 / 3)


def test_extraction_dedupes_double_predictions():
    gold = [("a", "b", "creditor")]
    predicted = [("a", "b", "creditor"), ("a", "b", "creditor")]
    m = extraction_metrics(predicted, gold)
    assert m.false_positives == 0
    assert m.precision == 1.0


def test_perfect_and_empty():
    assert extraction_metrics([], []).f1 == 0.0
    m = extraction_metrics([("a", "b", "creditor")], [("a", "b", "creditor")])
    assert m.f1 == 1.0


# --------------------------------------------------------------------------- #
# Entity resolution                                                            #
# --------------------------------------------------------------------------- #
def test_entity_resolution_accuracy():
    gold = {"JPM": "bank:jpm", "Chase": "bank:jpm", "BofA": "bank:bac"}
    resolved = [("JPM", "bank:jpm"), ("Chase", "bank:jpm"), ("BofA", "bank:wfc")]
    assert entity_resolution_accuracy(resolved, gold) == pytest.approx(2 / 3)


def test_entity_resolution_ignores_unlabeled():
    gold = {"JPM": "bank:jpm"}
    resolved = [("JPM", "bank:jpm"), ("Unknown Co", None)]
    assert entity_resolution_accuracy(resolved, gold) == 1.0


def test_entity_resolution_empty_raises():
    with pytest.raises(EvaluationError):
        entity_resolution_accuracy([], {})


# --------------------------------------------------------------------------- #
# Unsupported-claim rate (reuses the RIS-19 guard)                             #
# --------------------------------------------------------------------------- #
def test_unsupported_claim_rate():
    good = ("Score is 4.2 over 3 paths.", ExplanationPayload.from_values(4.2, 3))
    bad = ("Score is 4.2 but default risk 88%.", ExplanationPayload.from_values(4.2))
    assert unsupported_claim_rate([good, good]) == 0.0
    assert unsupported_claim_rate([good, bad]) == pytest.approx(0.5)


def test_unsupported_claim_rate_empty_is_zero():
    assert unsupported_claim_rate([]) == 0.0


# --------------------------------------------------------------------------- #
# Citation correctness, stability, latency                                     #
# --------------------------------------------------------------------------- #
def test_citation_correctness_rate():
    assert citation_correctness_rate([True, True, False, True]) == pytest.approx(0.75)
    with pytest.raises(EvaluationError):
        citation_correctness_rate([])


def test_scenario_stability():
    assert scenario_stability(["abc", "abc", "abc"]) is True
    assert scenario_stability(["abc", "abd"]) is False
    with pytest.raises(EvaluationError):
        scenario_stability([])


def test_latency_summary():
    s = latency_summary("propagation", [10.0, 12.0, 11.0, 100.0, 9.0])
    assert s.stage == "propagation"
    assert s.count == 5
    assert s.p50_ms == pytest.approx(11.0)
    assert s.max_ms == pytest.approx(100.0)
    with pytest.raises(EvaluationError):
        latency_summary("parse", [])


# --------------------------------------------------------------------------- #
# Labeling scaffold                                                            #
# --------------------------------------------------------------------------- #
def test_label_record_validates():
    label = LabeledRelationship(
        passage_id="p1",
        source_document_id="0000019617-24-000001",
        char_start=100,
        char_end=180,
        source_entity="JPMorgan Chase",
        target_entity="Some Borrower",
        relationship_type="creditor",
        is_relationship=True,
    )
    assert label.gold_key == ("JPMorgan Chase", "Some Borrower", "creditor")


def test_label_rejects_bad_relationship_type():
    with pytest.raises(LabelError):
        LabeledRelationship(
            passage_id="p1",
            source_document_id="d",
            char_start=0,
            char_end=10,
            source_entity="A",
            target_entity="B",
            relationship_type="made_up",
            is_relationship=True,
        )


def test_labels_round_trip_into_extraction_metrics():
    # A gold set of labels scores a prediction — the two modules compose.
    labels = [
        LabeledRelationship(
            passage_id=f"p{i}",
            source_document_id="d",
            char_start=i * 10,
            char_end=i * 10 + 5,
            source_entity=f"s{i}",
            target_entity=f"t{i}",
            relationship_type="creditor",
            is_relationship=True,
        )
        for i in range(3)
    ]
    gold = [label.gold_key for label in labels]
    predicted = [gold[0], gold[1]]  # missed one → recall 2/3
    m = extraction_metrics(predicted, gold)
    assert m.recall == pytest.approx(2 / 3)
    assert m.precision == 1.0

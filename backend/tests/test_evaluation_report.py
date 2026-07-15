"""Report-aggregator + committed-sample tests (RIS-21, `RW-OPS-001`, §15)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from riskweave.evaluation import run_evaluation
from riskweave.evaluation.labeling import (
    LabeledRelationship,
    LabelError,
    load_labels,
    positive_keys,
)
from riskweave.evaluation.report import (
    DEFAULT_LABELS_PATH,
    DEFAULT_PREDICTIONS_PATH,
    TARGET_EXTRACTION_PRECISION,
    TARGET_EXTRACTION_RECALL,
    citation_spot_checks,
    repeated_run_checksums,
)
from riskweave.graph.fixture import DEFAULT_FIXTURE_PATH, load_graph_fixture

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "evaluation" / "extraction_labels.jsonl"
PREDICTIONS = ROOT / "data" / "evaluation" / "extraction_predictions.jsonl"


# --------------------------------------------------------------------------- #
# Part A — the committed hand-labeled sample                                   #
# --------------------------------------------------------------------------- #
def test_labeled_sample_has_50_plus_passages_across_both_packs():
    labels = load_labels(str(LABELS))
    assert len(labels) >= 50
    assert {label.pack for label in labels} == {"cre", "oil"}


def test_labeled_sample_carries_notes_and_provenance_status():
    labels = load_labels(str(LABELS))
    assert all(label.notes for label in labels)
    assert {label.provenance_status for label in labels} == {
        "committed-fixture",
        "representative",
    }


def test_cre_predictions_mirror_the_committed_graph_fixture():
    """CRE predicted relationships must trace to the real-provenance fixture."""
    predictions = load_labels(str(PREDICTIONS))
    predicted_cre = {p.gold_key for p in predictions if p.pack == "cre"}

    graph = load_graph_fixture()
    name_by_edge = {(e.source_id, e.target_id): e for e in graph.edges}
    fixture = json.loads(DEFAULT_FIXTURE_PATH.read_text())
    name_by_id = {n["id"]: n["canonical_name"] for n in fixture["nodes"]}
    fixture_keys = {
        (name_by_id[e["source_id"]], name_by_id[e["target_id"]], e["relationship_type"])
        for e in fixture["edges"]
    }
    assert predicted_cre == fixture_keys
    assert len(name_by_edge) == len(fixture["edges"])  # no duplicate edges


# --------------------------------------------------------------------------- #
# Part A — label record metadata validation                                   #
# --------------------------------------------------------------------------- #
def test_label_accepts_new_optional_metadata():
    label = LabeledRelationship(
        passage_id="p",
        source_document_id="d",
        char_start=0,
        char_end=10,
        source_entity="A",
        target_entity="B",
        relationship_type="creditor",
        is_relationship=True,
        pack="cre",
        provenance_status="committed-fixture",
        extraction_confidence=0.9,
        notes="ok",
    )
    assert label.pack == "cre"


def test_label_rejects_bad_provenance_status():
    with pytest.raises(LabelError):
        LabeledRelationship(
            passage_id="p",
            source_document_id="d",
            char_start=0,
            char_end=10,
            source_entity="A",
            target_entity="B",
            relationship_type="creditor",
            is_relationship=True,
            provenance_status="made-up",
        )


def test_label_rejects_out_of_range_confidence():
    with pytest.raises(LabelError):
        LabeledRelationship(
            passage_id="p",
            source_document_id="d",
            char_start=0,
            char_end=10,
            source_entity="A",
            target_entity="B",
            relationship_type="creditor",
            is_relationship=True,
            extraction_confidence=1.5,
        )


def test_loader_rejects_unknown_field(tmp_path: Path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"passage_id":"p","source_document_id":"d","char_start":0,'
        '"char_end":5,"source_entity":"A","target_entity":"B",'
        '"relationship_type":"creditor","is_relationship":true,"bogus":1}\n'
    )
    with pytest.raises(LabelError):
        load_labels(str(bad))


# --------------------------------------------------------------------------- #
# Part B — pure metric building blocks                                         #
# --------------------------------------------------------------------------- #
def test_citation_spot_checks_pass_for_committed_fixture():
    graph = load_graph_fixture()
    checks = citation_spot_checks(graph)
    assert len(checks) == len(graph.edges)
    # The committed fixture's passages support every derived weight.
    assert all(checks)


def test_repeated_runs_are_bit_identical():
    graph = load_graph_fixture()
    checksums = repeated_run_checksums(graph, runs=4)
    assert len(set(checksums)) == 1


# --------------------------------------------------------------------------- #
# Part B — full report                                                         #
# --------------------------------------------------------------------------- #
def test_report_covers_all_six_families_and_hits_targets():
    report = run_evaluation(generated_at="test")
    by_key = {row.key: row for row in report.rows}

    # All six §15 metric families are represented.
    families = {row.family for row in report.rows}
    assert len(families) == 6

    # Extraction precision/recall computed from the committed sample.
    assert by_key["extraction_precision"].passed
    assert by_key["extraction_recall"].passed
    prec = float(by_key["extraction_precision"].actual_display.rstrip("%")) / 100
    rec = float(by_key["extraction_recall"].actual_display.rstrip("%")) / 100
    assert prec >= TARGET_EXTRACTION_PRECISION
    assert rec >= TARGET_EXTRACTION_RECALL

    # Every other family lands on target on real data.
    for key in (
        "entity_resolution_accuracy",
        "unsupported_claim_rate",
        "citation_correctness",
        "scenario_stability",
        "propagation_latency",
        "parse_latency",
    ):
        assert by_key[key].passed, f"{key} unexpectedly failing"

    assert report.all_passed
    assert report.snapshot_id
    assert report.generated_at == "test"


def test_report_serializes_for_the_api():
    payload = run_evaluation(generated_at="test").to_dict()
    assert payload["all_passed"] is True
    assert len(payload["families"]) == 6
    assert all(
        {"key", "label", "family", "actual_display", "passed"} <= row.keys()
        for row in payload["rows"]
    )


def test_default_paths_point_at_committed_files():
    assert DEFAULT_LABELS_PATH.exists()
    assert DEFAULT_PREDICTIONS_PATH.exists()
    gold = load_labels(str(DEFAULT_LABELS_PATH))
    pred = load_labels(str(DEFAULT_PREDICTIONS_PATH))
    assert len(positive_keys(gold)) > len(positive_keys(pred))  # gold has honest FNs

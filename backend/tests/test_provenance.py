"""Tests for the provenance invariant: no weight without complete provenance."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from riskweave.derivations import Provenance, ProvenanceError, WeightRecord


def _record_with(provenance) -> WeightRecord:
    return WeightRecord(
        value=0.28,
        method_id="DER-COMMODITY",
        method_version="1.0.0",
        inputs={"commodity_cost": 2800.0, "operating_expenses": 10000.0},
        provenance=provenance,
        data_timestamps=(datetime(2024, 2, 1),),
    )


def test_rejects_weight_without_provenance():
    """A WeightRecord cannot be built without a valid Provenance (the invariant)."""
    with pytest.raises(ProvenanceError):
        _record_with(None)
    with pytest.raises(ProvenanceError):
        _record_with("0000320193-24-000123")  # a bare id is not provenance


def test_accepts_weight_with_complete_provenance(provenance):
    record = _record_with(provenance)
    assert record.value == 0.28
    assert record.provenance is provenance


def test_weight_record_inputs_are_read_only(provenance):
    record = _record_with(provenance)
    with pytest.raises(TypeError):
        record.inputs["commodity_cost"] = 0.0  # type: ignore[index]


def test_offsets_must_match_passage_length():
    with pytest.raises(ProvenanceError):
        Provenance(
            source_document_id="doc-1",
            filing_date=date(2024, 1, 1),
            source_passage="28% of opex",
            char_start=0,
            char_end=5,  # too short for the passage
            data_timestamp=datetime(2024, 1, 1),
            extraction_confidence=0.9,
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan")])
def test_confidence_must_be_within_unit_interval(confidence):
    with pytest.raises(ProvenanceError):
        Provenance(
            source_document_id="doc-1",
            filing_date=date(2024, 1, 1),
            source_passage="x",
            char_start=0,
            char_end=1,
            data_timestamp=datetime(2024, 1, 1),
            extraction_confidence=confidence,
        )


@pytest.mark.parametrize("passage", ["", "   "])
def test_empty_passage_rejected(passage):
    with pytest.raises(ProvenanceError):
        Provenance(
            source_document_id="doc-1",
            filing_date=date(2024, 1, 1),
            source_passage=passage,
            char_start=0,
            char_end=len(passage),
            data_timestamp=datetime(2024, 1, 1),
            extraction_confidence=0.9,
        )


def test_non_finite_value_rejected(provenance):
    with pytest.raises(ProvenanceError):
        WeightRecord(
            value=float("inf"),
            method_id="DER-COMMODITY",
            method_version="1.0.0",
            inputs={},
            provenance=provenance,
            data_timestamps=(datetime(2024, 2, 1),),
        )


def test_empty_data_timestamps_rejected(provenance):
    with pytest.raises(ProvenanceError):
        WeightRecord(
            value=0.1,
            method_id="DER-COMMODITY",
            method_version="1.0.0",
            inputs={},
            provenance=provenance,
            data_timestamps=(),
        )

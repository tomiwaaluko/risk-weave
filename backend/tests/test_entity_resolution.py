from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from riskweave.entity_resolution import (
    ENTITY_RESOLUTION_CONFIDENCE_THRESHOLD,
    EntityRecord,
    GeminiMergeProposal,
    Resolver,
    load_universe,
    normalize_identifier,
    normalize_name,
)
from riskweave.evaluation import entity_resolution_accuracy

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "data/universe/entities.json"
SAMPLE = ROOT / "data/evaluation/entity_resolution_sample.json"


def _fixed_clock() -> datetime:
    return datetime(2026, 7, 11, 18, 0, tzinfo=UTC)


def test_deterministic_layer_resolves_all_exact_cik_and_ticker_mentions() -> None:
    resolver = Resolver(load_universe(UNIVERSE), clock=_fixed_clock)
    for entity in resolver.entities:
        for mention in (entity.cik, entity.ticker):
            if mention:
                result = resolver.resolve(mention)
                assert result.entity_id == entity.id
                assert result.layer == "deterministic"
                assert result.audit_event is not None
                assert result.audit_event.confidence == 1.0


def test_normalized_name_matching_handles_suffixes_punctuation_and_abbreviations() -> None:
    resolver = Resolver(load_universe(UNIVERSE), clock=_fixed_clock)
    assert resolver.resolve("JPMorgan Chase").entity_id == "bank:jpm"
    assert resolver.resolve("JPMorgan Chase & Co.").entity_id == "bank:jpm"
    assert resolver.resolve("C. H. Robinson Worldwide, Inc.").entity_id == (
        "transport_company:chrw"
    )
    assert normalize_name("Acme Intl Corp.") == "acme international"
    assert normalize_identifier("19617") == "0000019617"


def test_ambiguous_name_goes_to_queue_not_forced_match() -> None:
    resolver = Resolver(
        (
            EntityRecord("bank:alpha", "Alpha Bank Inc.", "bank", aliases=("Alpha",)),
            EntityRecord("reit:alpha", "Alpha REIT LLC", "reit", aliases=("Alpha",)),
        ),
        clock=_fixed_clock,
    )
    result = resolver.resolve("Alpha")
    assert result.entity_id is None
    assert result.unresolved is not None
    assert result.unresolved.reason == "ambiguous_deterministic_match"
    assert set(result.unresolved.candidates) == {"bank:alpha", "reit:alpha"}

    results, audits, unresolved = resolver.resolve_many(
        ["Alpha"],
        proposals=[
            GeminiMergeProposal(
                input_string="Alpha",
                candidate_entity_id="bank:alpha",
                confidence=0.95,
            )
        ],
    )
    assert results[0].entity_id is None
    assert audits == []
    assert unresolved[0].reason == "ambiguous_deterministic_match"


def test_gemini_residual_proposals_use_strict_json_and_threshold() -> None:
    resolver = Resolver(load_universe(UNIVERSE), clock=_fixed_clock)
    good = GeminiMergeProposal.model_validate(
        {
            "input_string": "Morgan Stnly",
            "candidate_entity_id": "bank:ms",
            "confidence": ENTITY_RESOLUTION_CONFIDENCE_THRESHOLD,
            "rationale": "Alias-like residual spelling.",
        }
    )
    low = GeminiMergeProposal.model_validate(
        {
            "input_string": "Mystery Chase",
            "candidate_entity_id": "bank:jpm",
            "confidence": 0.79,
        }
    )
    results, audits, unresolved = resolver.resolve_many(
        ["Morgan Stnly", "Mystery Chase"], proposals=[good, low]
    )
    by_input = {result.input_string: result for result in results}
    assert by_input["Morgan Stnly"].entity_id == "bank:ms"
    assert by_input["Morgan Stnly"].layer == "gemini_residual"
    assert audits[0].matched_entity_id == "bank:ms"
    assert by_input["Mystery Chase"].entity_id is None
    assert unresolved[0].reason == "proposal_below_threshold"

    with pytest.raises(ValidationError):
        GeminiMergeProposal.model_validate(
            {
                "input_string": "Bad extra",
                "candidate_entity_id": "bank:jpm",
                "confidence": 0.9,
                "estimated_sensitivity": 0.2,
            }
        )


def test_manual_corrections_are_append_only_inputs_to_reproducible_resolution(
    tmp_path: Path,
) -> None:
    corrections = tmp_path / "corrections.jsonl"
    corrections.write_text(
        json.dumps(
            {
                "input_string": "The Chase Manhattan successor",
                "entity_id": "bank:jpm",
                "reviewer": "fixture",
                "reason": "manual queue review",
                "timestamp": "2026-07-11T18:00:00+00:00",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    resolver = Resolver.from_universe_file(
        UNIVERSE, corrections_path=corrections, clock=_fixed_clock
    )
    first = resolver.resolve("The Chase Manhattan successor")
    second = resolver.resolve("The Chase Manhattan successor")
    assert first.entity_id == "bank:jpm"
    assert first.layer == "manual_correction"
    assert first.entity_id == second.entity_id
    assert first.audit_event == second.audit_event


def test_recorded_resolution_sample_precision_exceeds_target() -> None:
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    resolver = Resolver(load_universe(UNIVERSE), clock=_fixed_clock)
    resolved = [
        (sample["mention"], resolver.resolve(sample["mention"]).entity_id)
        for sample in payload["samples"]
    ]
    gold = {sample["mention"]: sample["expected_entity_id"] for sample in payload["samples"]}
    assert len(resolved) == 50
    assert entity_resolution_accuracy(resolved, gold) >= payload["expected_precision_floor"]


def test_merge_audit_log_complete_for_every_applied_merge() -> None:
    resolver = Resolver(load_universe(UNIVERSE), clock=_fixed_clock)
    results, audits, unresolved = resolver.resolve_many(
        ["JPM", "Morgan Stnly", "Unknown Name"],
        proposals=[
            GeminiMergeProposal(
                input_string="Morgan Stnly",
                candidate_entity_id="bank:ms",
                confidence=0.91,
                rationale="high-confidence residual",
            )
        ],
    )
    assert [result.entity_id for result in results] == ["bank:jpm", "bank:ms", None]
    assert len(audits) == 2
    assert len(unresolved) == 1
    for audit in audits:
        assert audit.input_string
        assert audit.matched_entity_id
        assert audit.layer in {"deterministic", "gemini_residual", "manual_correction"}
        assert 0.0 <= audit.confidence <= 1.0
        assert audit.timestamp == "2026-07-11T18:00:00+00:00"


def test_resolve_many_preserves_duplicate_mentions_for_auditability() -> None:
    resolver = Resolver(load_universe(UNIVERSE), clock=_fixed_clock)
    results, audits, unresolved = resolver.resolve_many(["JPM", "JPM"])
    assert [result.entity_id for result in results] == ["bank:jpm", "bank:jpm"]
    assert [audit.input_string for audit in audits] == ["JPM", "JPM"]
    assert unresolved == []

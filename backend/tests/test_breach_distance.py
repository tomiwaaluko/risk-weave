"""Breach-distance tests (RIS-16, Graft 1, `RW-ALG-030`).

Hand-computed on three covenant kinds; the regional-bank leverage beat from the
spec (§11: 4.2x today, 4.5x limit, 4.8x projected, headroom exhausted) is
verified end to end.
"""

from datetime import date, datetime

import pytest

from riskweave.breach import (
    BreachError,
    BreachTier,
    CovenantKind,
    CovenantThreshold,
    breach_distance,
    interest_coverage_ratio,
    leverage_ratio,
    liquidity_ratio,
    project_ratio,
)
from riskweave.derivations import Provenance


def prov(passage: str = "maintain a Total Leverage Ratio not to exceed 4.50 to 1.00") -> Provenance:
    return Provenance(
        source_document_id="0000019617-24-000042",
        filing_date=date(2024, 2, 15),
        source_passage=passage,
        char_start=8000,
        char_end=8000 + len(passage),
        data_timestamp=datetime(2024, 2, 15, 0, 0, 0),
        extraction_confidence=0.92,
    )


def leverage_threshold(value: float = 4.5) -> CovenantThreshold:
    return CovenantThreshold(
        entity_id="bank:example", kind=CovenantKind.LEVERAGE, value=value, provenance=prov()
    )


# --------------------------------------------------------------------------- #
# Ratio math (hand-computed)                                                   #
# --------------------------------------------------------------------------- #
def test_leverage_ratio_hand_computed():
    assert leverage_ratio(4200.0, 1000.0) == pytest.approx(4.2)


def test_interest_coverage_hand_computed():
    assert interest_coverage_ratio(600.0, 200.0) == pytest.approx(3.0)


def test_liquidity_ratio_hand_computed():
    assert liquidity_ratio(1500.0, 1000.0) == pytest.approx(1.5)


def test_ratios_reject_zero_denominator():
    with pytest.raises(BreachError):
        leverage_ratio(100.0, 0.0)
    with pytest.raises(BreachError):
        interest_coverage_ratio(100.0, 0.0)


# --------------------------------------------------------------------------- #
# Projection                                                                   #
# --------------------------------------------------------------------------- #
def test_leverage_rises_under_stress():
    # current 4.2, impact 0.1428... → 4.2 × 1.142857 = 4.8
    assert project_ratio(4.2, CovenantKind.LEVERAGE, 1.0 / 7.0) == pytest.approx(4.8)


def test_coverage_falls_under_stress():
    # coverage sensitivity is negative: 3.0 × (1 − 0.2) = 2.4
    assert project_ratio(3.0, CovenantKind.INTEREST_COVERAGE, 0.2) == pytest.approx(2.4)


def test_projection_floored_at_zero():
    assert project_ratio(1.5, CovenantKind.MIN_LIQUIDITY, 5.0) == 0.0


# --------------------------------------------------------------------------- #
# The regional-bank demo beat, end to end                                      #
# --------------------------------------------------------------------------- #
def test_regional_bank_leverage_beat():
    # §11: 4.2x today, 4.5x covenant, 4.8x projected → headroom exhausted.
    result = breach_distance(leverage_threshold(4.5), current_ratio=4.2, node_impact=1.0 / 7.0)
    assert result.current_value == pytest.approx(4.2)
    assert result.threshold_value == pytest.approx(4.5)
    assert result.projected_value == pytest.approx(4.8)
    assert result.headroom == pytest.approx(4.5 - 4.8)  # −0.3, breached
    assert result.tier is BreachTier.EXHAUSTED
    assert result.breached is True
    # The threshold is always traceable to the filing passage.
    assert "4.50 to 1.00" in result.threshold_provenance.source_passage


def test_tier_safe_when_shock_is_small():
    result = breach_distance(leverage_threshold(6.0), current_ratio=4.2, node_impact=0.01)
    assert result.tier is BreachTier.SAFE
    assert result.breached is False


def test_tier_thinning_between_safe_and_breach():
    # cushion 6.0−4.2 = 1.8; project 4.2 → 4.62 leaves headroom 1.38 (safe),
    # push harder to eat >75% of cushion.
    result = breach_distance(leverage_threshold(6.0), current_ratio=4.2, node_impact=0.35)
    # 4.2 × 1.35 = 5.67, headroom 0.33 < 0.25×1.8=0.45 → thinning
    assert result.projected_value == pytest.approx(5.67)
    assert result.tier is BreachTier.THINNING


def test_interest_coverage_breach():
    thr = CovenantThreshold(
        entity_id="corp:x",
        kind=CovenantKind.INTEREST_COVERAGE,
        value=2.0,
        provenance=prov("Interest Coverage Ratio of not less than 2.00 to 1.00"),
    )
    # coverage 3.0 falls under stress: 3.0 × (1−0.4) = 1.8 < 2.0 → breached
    result = breach_distance(thr, current_ratio=3.0, node_impact=0.4)
    assert result.projected_value == pytest.approx(1.8)
    assert result.tier is BreachTier.EXHAUSTED


# --------------------------------------------------------------------------- #
# Provenance gate: no covenant without evidence                                #
# --------------------------------------------------------------------------- #
def test_threshold_requires_provenance():
    with pytest.raises(BreachError):
        CovenantThreshold(
            entity_id="bank:x", kind=CovenantKind.LEVERAGE, value=4.5, provenance=None
        )


def test_threshold_rejects_nonpositive_value():
    with pytest.raises(BreachError):
        CovenantThreshold(
            entity_id="bank:x", kind=CovenantKind.LEVERAGE, value=0.0, provenance=prov()
        )


# --------------------------------------------------------------------------- #
# Live-slider behaviour: monotone in severity                                  #
# --------------------------------------------------------------------------- #
def test_projection_monotone_in_severity():
    thr = leverage_threshold(4.5)
    prev = 0.0
    for severity in (0.0, 0.05, 0.1, 0.15, 0.2):
        projected = breach_distance(thr, 4.2, severity).projected_value
        assert projected >= prev
        prev = projected

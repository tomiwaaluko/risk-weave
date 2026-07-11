"""Hand-computed fixture tests for the six DER-* methods.

Every expected number here is computed by hand from the inputs (a share, or a
known OLS beta from perfectly-linear returns), not captured as a snapshot.
"""

from __future__ import annotations

import pytest

from riskweave.derivations import (
    DerivationError,
    der_beta,
    der_commodity_cost_share,
    der_commodity_factor_beta,
    der_concentration_disclosed,
    der_concentration_segment_share,
    der_credit_portfolio_share,
    der_duration,
    der_geo_revenue_share,
    parse_disclosed_magnitude,
)


# --- DER-COMMODITY (primary: cost share) ---------------------------------- #
def test_commodity_cost_share_hand_computed(provenance):
    # 2800 / 10000 = 0.28
    record = der_commodity_cost_share(2800.0, 10000.0, provenance)
    assert record.value == pytest.approx(0.28)
    assert record.method_id == "DER-COMMODITY"
    assert record.method_version == "1.0.0"
    assert record.provenance is provenance
    assert record.data_timestamps


def test_commodity_cost_share_rejects_share_above_one(provenance):
    with pytest.raises(DerivationError):
        der_commodity_cost_share(12000.0, 10000.0, provenance)


def test_commodity_cost_share_rejects_zero_denominator(provenance):
    with pytest.raises(DerivationError):
        der_commodity_cost_share(2800.0, 0.0, provenance)


# --- DER-COMMODITY (fallback: factor beta) -------------------------------- #
def _linear_returns(slope: float, intercept: float, n: int = 30):
    x = [((i % 7) - 3) / 100.0 for i in range(n)]
    y = [intercept + slope * xi for xi in x]
    return y, x


def test_commodity_factor_beta_hand_computed(provenance):
    # asset = 0.8 * commodity exactly -> beta = 0.8
    asset, commodity = _linear_returns(slope=0.8, intercept=0.0)
    record = der_commodity_factor_beta(asset, commodity, provenance)
    assert record.value == pytest.approx(0.8, abs=1e-9)
    assert record.method_id == "DER-COMMODITY"


# --- DER-CONCENTRATION ---------------------------------------------------- #
def test_concentration_disclosed_from_parser(provenance):
    parsed = parse_disclosed_magnitude("approximately 28% of operating expenses")
    record = der_concentration_disclosed(parsed.value, provenance)
    assert record.value == pytest.approx(0.28)
    assert record.method_id == "DER-CONCENTRATION"


def test_concentration_disclosed_rejects_out_of_range(provenance):
    with pytest.raises(DerivationError):
        der_concentration_disclosed(1.4, provenance)


def test_concentration_segment_share_hand_computed(provenance):
    # 450 / 1500 = 0.30
    record = der_concentration_segment_share(450.0, 1500.0, provenance)
    assert record.value == pytest.approx(0.30)
    assert record.method_id == "DER-CONCENTRATION"


# --- DER-CREDIT ----------------------------------------------------------- #
def test_credit_portfolio_share_hand_computed(provenance):
    # 1200 / 8000 = 0.15
    record = der_credit_portfolio_share(1200.0, 8000.0, provenance)
    assert record.value == pytest.approx(0.15)
    assert record.method_id == "DER-CREDIT"


# --- DER-DURATION (full worked-example coverage lives in test_duration.py) - #
def test_duration_record_binds_method_and_provenance(provenance):
    record = der_duration(
        {"coupon_rate": 0.10, "yield_rate": 0.10, "years_to_maturity": 3.0, "payments_per_year": 1},
        provenance,
    )
    assert record.method_id == "DER-DURATION"
    assert record.method_version == "1.0.0"
    assert record.value == pytest.approx(2.4869, abs=5e-5)  # 2.7355 / 1.10
    assert record.provenance is provenance


# --- DER-GEO -------------------------------------------------------------- #
def test_geo_revenue_share_hand_computed(provenance):
    # 600 / 2000 = 0.30
    record = der_geo_revenue_share(600.0, 2000.0, provenance)
    assert record.value == pytest.approx(0.30)
    assert record.method_id == "DER-GEO"


# --- DER-BETA ------------------------------------------------------------- #
def test_beta_hand_computed(provenance):
    # asset = 0.001 + 1.5 * market exactly -> OLS beta = 1.5
    asset, market = _linear_returns(slope=1.5, intercept=0.001)
    record = der_beta(asset, market, provenance)
    assert record.value == pytest.approx(1.5, abs=1e-9)
    assert record.method_id == "DER-BETA"


def test_beta_can_be_negative(provenance):
    asset, market = _linear_returns(slope=-0.6, intercept=0.0)
    record = der_beta(asset, market, provenance)
    assert record.value == pytest.approx(-0.6, abs=1e-9)


def test_beta_deterministic(provenance):
    # OLS is closed-form: identical inputs give a byte-identical beta, no seed.
    asset, market = _linear_returns(slope=1.5, intercept=0.001)
    first = der_beta(asset, market, provenance)
    second = der_beta(asset, market, provenance)
    assert first.value == second.value


def test_beta_rejects_too_few_observations(provenance):
    asset, market = _linear_returns(slope=1.5, intercept=0.0, n=10)
    with pytest.raises(DerivationError):
        der_beta(asset, market, provenance)


def test_beta_rejects_mismatched_lengths(provenance):
    with pytest.raises(DerivationError):
        der_beta([0.01] * 30, [0.01] * 29, provenance)


def test_beta_rejects_zero_variance_market(provenance):
    asset = [((i % 7) - 3) / 100.0 for i in range(30)]
    market = [0.01] * 30  # no variance
    with pytest.raises(DerivationError):
        der_beta(asset, market, provenance)

"""DER-DURATION tests (RIS-17, Graft 3, `RW-ALG-031`).

Cited worked examples (acceptance criterion: match published examples to
4 decimal places):

[1] The classic Macaulay-duration worked example used in the CFA Level I
    fixed-income curriculum and Investopedia's "Macaulay Duration" article:
    a 3-year bond, $100 par, 10% ANNUAL coupon, priced at a 10% yield
    (price = par). Macaulay duration = 2.7355 years; modified duration
    = 2.7355 / 1.10 = 2.4869 years (2.486852 unrounded).

[2] A zero-coupon bond's Macaulay duration equals its maturity exactly
    (Fabozzi, "Bond Markets, Analysis and Strategies", duration chapter).

[3] Par-bond closed form (same source): for a bond priced at par,
    MacD_periods = (1+i)/i × (1 − (1+i)^(−n)). A 5-year 6% semiannual
    par bond at a 6% yield gives 8.7861 periods = 4.3931 years,
    modified 4.2651.

Beyond the cited fixtures, the closed form is cross-checked against a
brute-force discounted-cash-flow computation over a parameter grid, so the
formula's correctness is verified independently of any single textbook number.
"""

import math
from datetime import date, datetime

import pytest

from riskweave.derivations import (
    DerivationError,
    DurationError,
    Provenance,
    der_duration,
    get_method,
    macaulay_duration,
    modified_duration,
    rate_shock_price_impact,
)
from riskweave.propagation import (
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)


def brute_force_macaulay(
    coupon_rate: float,
    yield_rate: float,
    years: float,
    k: int,
) -> float:
    """Definitional Macaulay duration: PV-weighted mean time of cash flows."""
    n = round(years * k)
    c = coupon_rate / k  # per-period coupon as fraction of face
    i = yield_rate / k
    flows = [(t, c + (1.0 if t == n else 0.0)) for t in range(1, n + 1)]
    pv = [cf / (1.0 + i) ** t for t, cf in flows]
    price = sum(pv)
    weighted_periods = sum(t * v for (t, _), v in zip(flows, pv, strict=True))
    return weighted_periods / price / k


# --------------------------------------------------------------------------- #
# Cited worked examples (4-decimal acceptance criterion)                       #
# --------------------------------------------------------------------------- #
def test_macaulay_matches_cfa_worked_example():
    # [1] 3y, 10% annual coupon, 10% yield → 2.7355 years.
    assert macaulay_duration(0.10, 0.10, 3.0, 1) == pytest.approx(2.7355, abs=5e-5)


def test_modified_matches_cfa_worked_example():
    # [1] 2.7355 / 1.10 = 2.4869 years.
    assert modified_duration(0.10, 0.10, 3.0, 1) == pytest.approx(2.4869, abs=5e-5)


def test_zero_coupon_macaulay_equals_maturity():
    # [2] Zero-coupon: duration is the maturity, at any yield/frequency.
    assert macaulay_duration(0.0, 0.06, 5.0, 2) == pytest.approx(5.0, abs=1e-12)
    assert macaulay_duration(0.0, 0.11, 7.0, 1) == pytest.approx(7.0, abs=1e-12)


def test_par_bond_matches_closed_form():
    # [3] 5y 6% semiannual par bond at 6%: 4.3931 Macaulay, 4.2651 modified.
    i, n = 0.03, 10
    expected_periods = (1 + i) / i * (1 - (1 + i) ** -n)
    assert macaulay_duration(0.06, 0.06, 5.0, 2) == pytest.approx(expected_periods / 2, abs=1e-12)
    assert macaulay_duration(0.06, 0.06, 5.0, 2) == pytest.approx(4.3931, abs=5e-5)
    assert modified_duration(0.06, 0.06, 5.0, 2) == pytest.approx(4.2651, abs=5e-5)


# --------------------------------------------------------------------------- #
# Independent cross-check of the closed form                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("coupon", [0.0, 0.02, 0.06, 0.12])
@pytest.mark.parametrize("yld", [0.0, 0.01, 0.05, 0.15])
@pytest.mark.parametrize("years,k", [(1.0, 1), (5.0, 2), (2.5, 2), (10.0, 4), (0.5, 12)])
def test_closed_form_matches_brute_force(coupon, yld, years, k):
    closed = macaulay_duration(coupon, yld, years, k)
    brute = brute_force_macaulay(coupon, yld, years, k)
    assert closed == pytest.approx(brute, rel=1e-12, abs=1e-12)


def test_zero_yield_branch_is_exact():
    # i = 0 uses a dedicated closed form; check against the definition.
    assert macaulay_duration(0.08, 0.0, 4.0, 2) == pytest.approx(
        brute_force_macaulay(0.08, 0.0, 4.0, 2), abs=1e-12
    )


# --------------------------------------------------------------------------- #
# Validation: reject, don't guess                                              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "coupon,yld,years,k",
    [
        (-0.01, 0.05, 5.0, 2),  # negative coupon
        (0.05, -0.02, 5.0, 2),  # negative yield
        (0.05, 0.05, 0.0, 2),  # zero maturity
        (0.05, 0.05, -1.0, 2),  # negative maturity
        (0.05, 0.05, 5.0, 3),  # unsupported frequency
        (0.05, 0.05, 5.3, 1),  # fractional number of periods
        (float("nan"), 0.05, 5.0, 2),
        (0.05, float("inf"), 5.0, 2),
    ],
)
def test_rejects_invalid_terms(coupon, yld, years, k):
    with pytest.raises(DurationError):
        macaulay_duration(coupon, yld, years, k)


# --------------------------------------------------------------------------- #
# Transmission function: ΔP/P ≈ −ModD × Δy                                     #
# --------------------------------------------------------------------------- #
def test_rate_shock_price_impact_signs():
    d = modified_duration(0.10, 0.10, 3.0, 1)  # 2.486852
    assert rate_shock_price_impact(d, +0.01) == pytest.approx(-0.0248685, abs=5e-7)
    assert rate_shock_price_impact(d, -0.01) == pytest.approx(+0.0248685, abs=5e-7)
    assert rate_shock_price_impact(d, 0.0) == 0.0


def test_rate_shock_price_impact_rejects_bad_inputs():
    with pytest.raises(DurationError):
        rate_shock_price_impact(-1.0, 0.01)
    with pytest.raises(DurationError):
        rate_shock_price_impact(float("nan"), 0.01)


# --------------------------------------------------------------------------- #
# der_duration: WeightRecord with complete provenance                          #
# --------------------------------------------------------------------------- #
@pytest.fixture
def bond_provenance() -> Provenance:
    passage = "The 2029 Notes bear interest at 10% per annum, payable annually"
    return Provenance(
        source_document_id="0000000000-26-000042",
        filing_date=date(2026, 2, 15),
        source_passage=passage,
        char_start=52_000,
        char_end=52_000 + len(passage),
        data_timestamp=datetime(2026, 2, 15, 0, 0, 0),
        extraction_confidence=0.9,
    )


TERMS = {
    "coupon_rate": 0.10,
    "yield_rate": 0.10,
    "years_to_maturity": 3.0,
    "payments_per_year": 1,
}


def test_duration_weight_has_complete_provenance(bond_provenance):
    yield_asof = datetime(2026, 7, 10, 16, 0, 0)
    record = der_duration(TERMS, bond_provenance, yield_timestamp=yield_asof)
    assert record.value == pytest.approx(2.4869, abs=5e-5)
    assert record.method_id == "DER-DURATION"
    assert record.method_version == get_method("DER-DURATION").version == "1.0.0"
    assert record.provenance is bond_provenance
    # Both the filing timestamp and the yield-series as-of are recorded.
    assert record.data_timestamps == (bond_provenance.data_timestamp, yield_asof)
    assert record.inputs["macaulay_duration_years"] == pytest.approx(2.7355, abs=5e-5)
    assert record.inputs["payments_per_year"] == 1.0


def test_duration_rejects_missing_and_unknown_terms(bond_provenance):
    with pytest.raises(DerivationError):
        der_duration({"coupon_rate": 0.1, "yield_rate": 0.1}, bond_provenance)
    with pytest.raises(DerivationError):
        der_duration({**TERMS, "convexity": 12.0}, bond_provenance)


def test_duration_rejects_invalid_terms_as_derivation_error(bond_provenance):
    with pytest.raises(DerivationError):
        der_duration({**TERMS, "years_to_maturity": -1.0}, bond_provenance)


# --------------------------------------------------------------------------- #
# End-to-end: a rate scenario propagating through a duration edge              #
# --------------------------------------------------------------------------- #
def test_rate_scenario_propagates_through_duration_edge(bond_provenance):
    """Hand-checked path: rates +100 bp → bond (duration edge) → issuer.

    The rate-factor edge weight is −ModD, so first-order impact is exactly
    the Graft 3 transmission ΔP/P = −ModD × Δy; the second hop applies the
    ADR-001 damping to a DER-CREDIT edge.
    """
    record = der_duration(TERMS, bond_provenance)
    mod_dur = record.value  # 2.486852

    snap = GraphSnapshot(
        snapshot_id="snap-rates",
        graph_version="1.0.0",
        nodes=(
            GraphNode(node_id="rates_us", node_type="factor", name="US policy rate"),
            GraphNode(node_id="bond_2029", node_type="security", name="2029 Notes"),
            GraphNode(node_id="issuer", node_type="company", name="Issuer Corp"),
        ),
        edges=(
            GraphEdge(
                edge_id="rate>bond",
                source_id="rates_us",
                target_id="bond_2029",
                weight=-mod_dur,
                method_id=record.method_id,
                provenance_ref=record.provenance.source_document_id,
            ),
            GraphEdge(
                edge_id="bond>issuer",
                source_id="bond_2029",
                target_id="issuer",
                weight=0.5,
                method_id="DER-CREDIT",
                provenance_ref="prov:bond>issuer",
            ),
        ),
    )
    delta_yield = 0.01  # +100 bp
    result = propagate(
        snap,
        Scenario(
            scenario_id="scn-rates",
            factors=(
                ShockFactor(factor_id="rate-shock", node_id="rates_us", magnitude=delta_yield),
            ),
        ),
    )

    # First order: engine result equals the transmission function exactly.
    expected_bond = rate_shock_price_impact(mod_dur, delta_yield)  # −0.0248685
    assert result.impacts["bond_2029"].raw_impact == pytest.approx(expected_bond, abs=1e-12)
    # Second order, hand-computed: 0.01 × (−2.4868) × 0.5 × 0.6 = −0.0074604.
    assert result.impacts["issuer"].raw_impact == pytest.approx(-0.0074604, abs=5e-7)
    assert result.impacts["issuer"].risk_score == pytest.approx(
        100.0 * (1.0 - math.exp(-0.0074604)), abs=5e-5
    )
    # The duration edge surfaces its method id and provenance in the path.
    hop = result.impacts["issuer"].contributions[0].edges[0]
    assert hop.method_id == "DER-DURATION"
    assert hop.provenance_ref == "0000000000-26-000042"

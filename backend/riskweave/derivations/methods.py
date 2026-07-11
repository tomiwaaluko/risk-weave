"""The six registered deterministic derivation methods (spec §12.1).

Each function is **pure**: it takes already-fetched numbers (XBRL line items,
disclosure fractions, or return series) plus the ``Provenance`` they were read
from, and returns a fully-provenanced :class:`WeightRecord`. No function here
touches a database, a network, or a clock — that wiring belongs to ingestion
(RIS-8), keeping this library independent of the data contract.

Not a single number is estimated by a model anywhere in this module
(`RW-ALG-001`, `RW-AI-010`): every value is arithmetic or a closed-form OLS fit
on caller-supplied inputs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

import numpy as np
import statsmodels.api as sm

from .duration import DurationError, macaulay_duration
from .provenance import Provenance, WeightRecord
from .registry import get_method

# Minimum observations for a defensible OLS beta. Below this the regression is
# too thin to report; we refuse rather than emit a fragile number.
MIN_REGRESSION_OBS = 24


class DerivationError(ValueError):
    """Raised when inputs to a derivation are invalid or out of range."""


def _weight(
    method_id: str,
    value: float,
    inputs: Mapping[str, float],
    provenance: Provenance,
    data_timestamps: Sequence[datetime],
) -> WeightRecord:
    """Build a ``WeightRecord``, stamping the method version from the registry."""
    method = get_method(method_id)
    return WeightRecord(
        value=float(value),
        method_id=method_id,
        method_version=method.version,
        inputs=dict(inputs),
        provenance=provenance,
        data_timestamps=tuple(data_timestamps),
    )


def _require_positive(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DerivationError(f"{name} must be a real number")
    if not value > 0:
        raise DerivationError(f"{name} must be positive, got {value}")


def _require_nonnegative(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DerivationError(f"{name} must be a real number")
    if value < 0:
        raise DerivationError(f"{name} must be non-negative, got {value}")


def _share(numerator: float, denominator: float, num_name: str, den_name: str) -> float:
    """A share in ``[0, 1]``; reject data errors that would produce > 1."""
    _require_nonnegative(num_name, numerator)
    _require_positive(den_name, denominator)
    value = numerator / denominator
    if value > 1.0:
        raise DerivationError(
            f"{num_name} ({numerator}) exceeds {den_name} ({denominator}); "
            "share would be > 1, which is a data error"
        )
    return value


# --------------------------------------------------------------------------- #
# DER-COMMODITY                                                                #
# --------------------------------------------------------------------------- #
def der_commodity_cost_share(
    commodity_cost: float,
    operating_expenses: float,
    provenance: Provenance,
) -> WeightRecord:
    """Primary DER-COMMODITY: commodity cost as a share of operating expenses.

    e.g. jet fuel cost / total operating expenses, both from XBRL.
    """
    value = _share(commodity_cost, operating_expenses, "commodity_cost", "operating_expenses")
    return _weight(
        "DER-COMMODITY",
        value,
        {"commodity_cost": commodity_cost, "operating_expenses": operating_expenses},
        provenance,
        (provenance.data_timestamp,),
    )


def der_commodity_factor_beta(
    asset_returns: Sequence[float],
    commodity_returns: Sequence[float],
    provenance: Provenance,
) -> WeightRecord:
    """Fallback DER-COMMODITY: OLS factor beta of the asset on the commodity.

    Used when no cost-line share is disclosed. Sign is meaningful (a negative
    beta is a hedge/beneficiary); callers interpret direction separately.
    """
    beta, _ = _ols_slope(asset_returns, commodity_returns, "commodity_returns")
    return _weight(
        "DER-COMMODITY",
        beta,
        {"n_observations": float(len(asset_returns))},
        provenance,
        (provenance.data_timestamp,),
    )


# --------------------------------------------------------------------------- #
# DER-CONCENTRATION                                                            #
# --------------------------------------------------------------------------- #
def der_concentration_disclosed(
    disclosed_fraction: float,
    provenance: Provenance,
) -> WeightRecord:
    """Primary DER-CONCENTRATION: a validated, disclosed concentration fraction.

    ``disclosed_fraction`` must already be the output of
    :func:`riskweave.derivations.magnitude.parse_disclosed_magnitude` (a fraction
    in ``[0, 1]``), so the verbatim → number conversion stays deterministic and
    auditable.
    """
    if not isinstance(disclosed_fraction, (int, float)) or isinstance(disclosed_fraction, bool):
        raise DerivationError("disclosed_fraction must be a real number")
    if not (0.0 <= disclosed_fraction <= 1.0):
        raise DerivationError(
            f"disclosed_fraction must be a fraction in [0, 1], got {disclosed_fraction}"
        )
    return _weight(
        "DER-CONCENTRATION",
        disclosed_fraction,
        {"disclosed_fraction": disclosed_fraction},
        provenance,
        (provenance.data_timestamp,),
    )


def der_concentration_segment_share(
    segment_revenue: float,
    total_revenue: float,
    provenance: Provenance,
) -> WeightRecord:
    """Fallback DER-CONCENTRATION: segment revenue over total revenue (XBRL)."""
    value = _share(segment_revenue, total_revenue, "segment_revenue", "total_revenue")
    return _weight(
        "DER-CONCENTRATION",
        value,
        {"segment_revenue": segment_revenue, "total_revenue": total_revenue},
        provenance,
        (provenance.data_timestamp,),
    )


# --------------------------------------------------------------------------- #
# DER-CREDIT                                                                   #
# --------------------------------------------------------------------------- #
def der_credit_portfolio_share(
    exposure_amount: float,
    total_loan_portfolio: float,
    provenance: Provenance,
) -> WeightRecord:
    """DER-CREDIT: exposure to a borrower/segment over the total loan portfolio.

    From bank 10-K/10-Q loan-portfolio composition disclosures.
    """
    value = _share(exposure_amount, total_loan_portfolio, "exposure_amount", "total_loan_portfolio")
    return _weight(
        "DER-CREDIT",
        value,
        {"exposure_amount": exposure_amount, "total_loan_portfolio": total_loan_portfolio},
        provenance,
        (provenance.data_timestamp,),
    )


# --------------------------------------------------------------------------- #
# DER-DURATION (Graft 3, RW-ALG-031)                                           #
# --------------------------------------------------------------------------- #
def der_duration(
    security_terms: Mapping[str, float],
    provenance: Provenance,
    yield_timestamp: datetime | None = None,
) -> WeightRecord:
    """DER-DURATION: closed-form modified duration of a debt instrument.

    ``security_terms`` carries the bond/debt terms read from filings:
    ``coupon_rate`` and ``yield_rate`` as annual decimals, ``years_to_maturity``,
    and optionally ``payments_per_year`` (default 2, semiannual). ``provenance``
    quotes the filing passage the terms came from; ``yield_timestamp`` is the
    as-of of the current-yield input (FRED series observation) and is recorded
    alongside the filing timestamp (`RW-ALG-032`).

    The record's ``value`` is the (non-negative) modified duration in years.
    For rate-shock transmission, the rate-factor edge weight is ``-value`` so
    the engine's first-order rule reproduces ``ΔP/P ≈ −ModD × Δy`` — see
    :mod:`riskweave.derivations.duration`.
    """
    terms = dict(security_terms)
    try:
        coupon_rate = terms.pop("coupon_rate")
        yield_rate = terms.pop("yield_rate")
        years_to_maturity = terms.pop("years_to_maturity")
    except KeyError as missing:
        raise DerivationError(f"security_terms is missing {missing.args[0]!r}") from None
    payments_per_year = int(terms.pop("payments_per_year", 2))
    if terms:
        raise DerivationError(f"unexpected security_terms keys: {sorted(terms)}")

    try:
        macaulay = macaulay_duration(coupon_rate, yield_rate, years_to_maturity, payments_per_year)
    except DurationError as exc:
        raise DerivationError(str(exc)) from exc
    value = macaulay / (1.0 + yield_rate / payments_per_year)

    timestamps = [provenance.data_timestamp]
    if yield_timestamp is not None:
        timestamps.append(yield_timestamp)
    return _weight(
        "DER-DURATION",
        value,
        {
            "coupon_rate": coupon_rate,
            "yield_rate": yield_rate,
            "years_to_maturity": years_to_maturity,
            "payments_per_year": float(payments_per_year),
            "macaulay_duration_years": macaulay,
        },
        provenance,
        timestamps,
    )


# --------------------------------------------------------------------------- #
# DER-GEO                                                                      #
# --------------------------------------------------------------------------- #
def der_geo_revenue_share(
    geography_revenue: float,
    total_revenue: float,
    provenance: Provenance,
) -> WeightRecord:
    """DER-GEO: revenue in a geography over total revenue (XBRL segments)."""
    value = _share(geography_revenue, total_revenue, "geography_revenue", "total_revenue")
    return _weight(
        "DER-GEO",
        value,
        {"geography_revenue": geography_revenue, "total_revenue": total_revenue},
        provenance,
        (provenance.data_timestamp,),
    )


# --------------------------------------------------------------------------- #
# DER-BETA                                                                     #
# --------------------------------------------------------------------------- #
def der_beta(
    asset_returns: Sequence[float],
    market_returns: Sequence[float],
    provenance: Provenance,
) -> WeightRecord:
    """DER-BETA: OLS beta of the asset on the market from historical returns.

    Equity-price source for the market/asset series is documented in the
    package README (`RW-DATA-002`). This function consumes pre-fetched daily
    return series; it does not fetch. OLS is closed-form and therefore fully
    deterministic — identical inputs give an identical beta with no seed.
    """
    beta, _ = _ols_slope(asset_returns, market_returns, "market_returns")
    return _weight(
        "DER-BETA",
        beta,
        {"n_observations": float(len(asset_returns))},
        provenance,
        (provenance.data_timestamp,),
    )


# --------------------------------------------------------------------------- #
# Shared OLS helper                                                            #
# --------------------------------------------------------------------------- #
def _ols_slope(
    y_returns: Sequence[float],
    x_returns: Sequence[float],
    x_name: str,
) -> tuple[float, object]:
    """Return the OLS slope (beta) of ``y`` on ``x`` with an intercept.

    Deterministic closed-form fit via statsmodels. Raises ``DerivationError``
    for malformed, too-short, or degenerate (no-variance) inputs rather than
    returning a fragile or undefined number.
    """
    y = np.asarray(y_returns, dtype=float)
    x = np.asarray(x_returns, dtype=float)
    if y.ndim != 1 or x.ndim != 1:
        raise DerivationError("returns must be one-dimensional sequences")
    if y.shape != x.shape:
        raise DerivationError(
            f"asset_returns and {x_name} must be the same length: {y.shape} vs {x.shape}"
        )
    if y.size < MIN_REGRESSION_OBS:
        raise DerivationError(
            f"need at least {MIN_REGRESSION_OBS} observations for a beta, got {y.size}"
        )
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(x)):
        raise DerivationError("returns contain non-finite values")
    if np.isclose(x.var(), 0.0):
        raise DerivationError(f"{x_name} has no variance; beta is undefined")
    design = sm.add_constant(x)
    fit = sm.OLS(y, design).fit()
    beta = float(fit.params[1])
    return beta, fit

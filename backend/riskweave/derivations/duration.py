"""Closed-form bond duration — Graft 3 (`RW-ALG-031`, spec §11, §12.1).

One function, one edge-weight type: modified duration as the deterministic
coefficient for how a rate move propagates to a debt instrument or debt-heavy
issuer. **Hard scope guard:** no yield-curve bootstrapping, no convexity, no
OAS, no bond similarity — all of that is `RW-ALG-D11`, DEFERRED.

The Macaulay duration of a level-coupon bond is computed in closed form (no
cash-flow loops, no solver). With per-period yield ``i = y/k``, per-period
coupon rate ``c = C/k`` (as a fraction of face) and ``n = k·T`` whole periods:

    MacD_periods = (1+i)/i − [ (1+i) + n(c−i) ] / [ c((1+i)^n − 1) + i ]      (i > 0)
    MacD_periods = [ c·n(n+1)/2 + n ] / (c·n + 1)                             (i = 0)

    MacD_years   = MacD_periods / k
    ModD         = MacD_years / (1 + i)

Both formulas are standard (Fabozzi, *Bond Markets, Analysis and Strategies*;
CFA Level I fixed-income curriculum) and reduce to ``MacD_years = T`` for a
zero-coupon bond.

Rate-shock transmission uses the first-order price approximation

    ΔP/P ≈ −ModD × Δy

wired into the propagation engine by giving the rate-factor → security edge a
weight of ``−ModD``: the engine's first-order rule (impact = magnitude × weight,
ADR-001) then yields exactly ΔP/P when the scenario magnitude is Δy.
"""

from __future__ import annotations

import math


class DurationError(ValueError):
    """Raised when bond terms are invalid for a closed-form duration."""


_ALLOWED_FREQUENCIES = (1, 2, 4, 12)


def _validate_terms(
    coupon_rate: float,
    yield_rate: float,
    years_to_maturity: float,
    payments_per_year: int,
) -> int:
    """Validate bond terms; return the whole number of coupon periods."""
    for name, value in (
        ("coupon_rate", coupon_rate),
        ("yield_rate", yield_rate),
        ("years_to_maturity", years_to_maturity),
    ):
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise DurationError(f"{name} must be a real number")
        if math.isnan(value) or math.isinf(value):
            raise DurationError(f"{name} must be finite")
    if coupon_rate < 0:
        raise DurationError(f"coupon_rate must be non-negative, got {coupon_rate}")
    if yield_rate < 0:
        raise DurationError(f"yield_rate must be non-negative, got {yield_rate}")
    if years_to_maturity <= 0:
        raise DurationError(f"years_to_maturity must be positive, got {years_to_maturity}")
    if payments_per_year not in _ALLOWED_FREQUENCIES:
        raise DurationError(
            f"payments_per_year must be one of {_ALLOWED_FREQUENCIES}, got {payments_per_year}"
        )
    n_exact = years_to_maturity * payments_per_year
    n = round(n_exact)
    if n < 1 or abs(n_exact - n) > 1e-9:
        raise DurationError(
            "years_to_maturity × payments_per_year must be a whole number of "
            f"coupon periods, got {n_exact}; reject rather than guess a stub period"
        )
    return n


def macaulay_duration(
    coupon_rate: float,
    yield_rate: float,
    years_to_maturity: float,
    payments_per_year: int = 2,
) -> float:
    """Macaulay duration in **years**, closed form.

    ``coupon_rate`` and ``yield_rate`` are annual decimals (0.06 = 6%);
    ``payments_per_year`` is the coupon frequency (semiannual default).
    """
    n = _validate_terms(coupon_rate, yield_rate, years_to_maturity, payments_per_year)
    k = payments_per_year
    c = coupon_rate / k
    i = yield_rate / k
    if i == 0.0:
        periods = (c * n * (n + 1) / 2.0 + n) / (c * n + 1.0)
    else:
        growth = (1.0 + i) ** n
        periods = (1.0 + i) / i - ((1.0 + i) + n * (c - i)) / (c * (growth - 1.0) + i)
    return periods / k


def modified_duration(
    coupon_rate: float,
    yield_rate: float,
    years_to_maturity: float,
    payments_per_year: int = 2,
) -> float:
    """Modified duration in years: ``MacD / (1 + y/k)``."""
    macaulay = macaulay_duration(coupon_rate, yield_rate, years_to_maturity, payments_per_year)
    return macaulay / (1.0 + yield_rate / payments_per_year)


def rate_shock_price_impact(mod_duration: float, delta_yield: float) -> float:
    """First-order price impact of a parallel rate move: ``ΔP/P ≈ −ModD × Δy``.

    ``delta_yield`` is the signed absolute yield change in decimals
    (+0.01 = rates up 100 bp). This is the Graft 3 transmission function; the
    propagation engine reproduces it when the rate-factor edge weight is
    ``−ModD`` and the scenario magnitude is ``Δy``.
    """
    for name, value in (("mod_duration", mod_duration), ("delta_yield", delta_yield)):
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise DurationError(f"{name} must be a real number")
        if math.isnan(value) or math.isinf(value):
            raise DurationError(f"{name} must be finite")
    if mod_duration < 0:
        raise DurationError(f"mod_duration must be non-negative, got {mod_duration}")
    return -mod_duration * delta_yield

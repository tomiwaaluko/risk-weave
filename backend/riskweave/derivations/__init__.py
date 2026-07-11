"""Deterministic edge-weight derivation library (spec §12.1).

Public surface for the six registered `DER-*` methods, the provenance-bound
``WeightRecord`` type, the disclosed-magnitude parser, and the method registry.
"""

from .duration import (
    DurationError,
    macaulay_duration,
    modified_duration,
    rate_shock_price_impact,
)
from .magnitude import MagnitudeParseError, ParsedMagnitude, parse_disclosed_magnitude
from .methods import (
    MIN_REGRESSION_OBS,
    DerivationError,
    der_beta,
    der_commodity_cost_share,
    der_commodity_factor_beta,
    der_concentration_disclosed,
    der_concentration_segment_share,
    der_credit_portfolio_share,
    der_duration,
    der_geo_revenue_share,
)
from .provenance import Provenance, ProvenanceError, WeightRecord
from .registry import (
    REGISTRY,
    DerivationMethod,
    UnknownMethodError,
    get_method,
    list_methods,
)

__all__ = [
    "Provenance",
    "ProvenanceError",
    "WeightRecord",
    "MagnitudeParseError",
    "ParsedMagnitude",
    "parse_disclosed_magnitude",
    "DerivationError",
    "DurationError",
    "macaulay_duration",
    "modified_duration",
    "rate_shock_price_impact",
    "MIN_REGRESSION_OBS",
    "der_commodity_cost_share",
    "der_commodity_factor_beta",
    "der_concentration_disclosed",
    "der_concentration_segment_share",
    "der_credit_portfolio_share",
    "der_duration",
    "der_geo_revenue_share",
    "der_beta",
    "REGISTRY",
    "DerivationMethod",
    "UnknownMethodError",
    "get_method",
    "list_methods",
]

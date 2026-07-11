"""Registry of the six registered deterministic derivation methods (spec §12.1).

Every edge weight entering propagation must name one of these method ids
(`RW-ALG-001`). The registry is the single source of truth for method id →
version → spec row, so a ``WeightRecord`` cannot claim a method that does not
exist, and its version string is stamped from here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


class UnknownMethodError(KeyError):
    """Raised when a method id is not in the registry."""


@dataclass(frozen=True)
class DerivationMethod:
    """Metadata for one registered `DER-*` method."""

    method_id: str
    version: str
    spec_row: str  # the §12.1 "Edge / exposure type" label
    source_data: str  # the §12.1 "Source data" column
    summary: str  # the deterministic derivation, one line
    variants: tuple[str, ...]  # callables implementing it (primary first)


_METHODS: dict[str, DerivationMethod] = {
    "DER-COMMODITY": DerivationMethod(
        method_id="DER-COMMODITY",
        version="1.0.0",
        spec_row="Commodity dependency (e.g. jet fuel)",
        source_data="XBRL, FRED/commodity history, market returns",
        summary=(
            "Cost-line share of operating expenses from XBRL; "
            "else factor beta vs the commodity series"
        ),
        variants=("der_commodity_cost_share", "der_commodity_factor_beta"),
    ),
    "DER-CONCENTRATION": DerivationMethod(
        method_id="DER-CONCENTRATION",
        version="1.0.0",
        spec_row="Supplier / customer dependency",
        source_data="10-K concentration disclosures, XBRL segments",
        summary=(
            "Disclosed revenue-concentration percentage (validated verbatim); "
            "else segment revenue share"
        ),
        variants=("der_concentration_disclosed", "der_concentration_segment_share"),
    ),
    "DER-CREDIT": DerivationMethod(
        method_id="DER-CREDIT",
        version="1.0.0",
        spec_row="Creditor / lending exposure",
        source_data="Bank 10-K/10-Q disclosures",
        summary="Loan-portfolio composition: exposure to a segment over total loan portfolio",
        variants=("der_credit_portfolio_share",),
    ),
    "DER-DURATION": DerivationMethod(
        method_id="DER-DURATION",
        version="0.0.0",  # stub; closed-form lands in RIS-17 (Graft 3)
        spec_row="Interest-rate sensitivity (debt / security nodes)",
        source_data="Bond terms from filings, current yield inputs",
        summary="Modified duration, closed-form (Graft 3) — implemented in RIS-17",
        variants=("der_duration",),
    ),
    "DER-GEO": DerivationMethod(
        method_id="DER-GEO",
        version="1.0.0",
        spec_row="Geographic exposure",
        source_data="XBRL",
        summary="Revenue-by-geography over total revenue from XBRL segment reporting",
        variants=("der_geo_revenue_share",),
    ),
    "DER-BETA": DerivationMethod(
        method_id="DER-BETA",
        version="1.0.0",
        spec_row="Equity market sensitivity",
        source_data="Market history",
        summary="OLS beta from historical returns regression of the asset on the market",
        variants=("der_beta",),
    ),
}

REGISTRY: Mapping[str, DerivationMethod] = MappingProxyType(_METHODS)


def get_method(method_id: str) -> DerivationMethod:
    """Return the registered method, or raise ``UnknownMethodError``."""
    try:
        return _METHODS[method_id]
    except KeyError:
        raise UnknownMethodError(f"unregistered derivation method id: {method_id!r}") from None


def list_methods() -> tuple[DerivationMethod, ...]:
    """Return all registered methods, in stable id order."""
    return tuple(_METHODS[k] for k in sorted(_METHODS))

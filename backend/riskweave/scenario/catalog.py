"""Supported shock factor catalog for `RW-FR-007`.

Natural-language parsing may map user text only onto these factor ids. Unknown
concepts remain unsupported validation issues rather than improvised factors.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorDefinition:
    factor_id: str
    label: str
    units: frozenset[str]
    min_magnitude: float
    max_magnitude: float
    default_unit: str
    default_path: str
    supported_directions: frozenset[str]
    scenario_packs: frozenset[str]


SUPPORTED_FACTORS: dict[str, FactorDefinition] = {
    "cre_property_value": FactorDefinition(
        factor_id="cre_property_value",
        label="Commercial real-estate value",
        units=frozenset({"percent"}),
        min_magnitude=0.0,
        max_magnitude=80.0,
        default_unit="percent",
        default_path="CRE value decline -> owners -> lenders -> credit tightening",
        supported_directions=frozenset({"down"}),
        scenario_packs=frozenset({"cre"}),
    ),
    "refinancing_rate": FactorDefinition(
        factor_id="refinancing_rate",
        label="Refinancing rate",
        units=frozenset({"basis_points"}),
        min_magnitude=0.0,
        max_magnitude=1000.0,
        default_unit="basis_points",
        default_path="Rates -> debt service -> refinancing stress",
        supported_directions=frozenset({"up", "down"}),
        scenario_packs=frozenset({"cre", "oil"}),
    ),
    "stress_duration": FactorDefinition(
        factor_id="stress_duration",
        label="Stress duration",
        units=frozenset({"quarters", "months"}),
        min_magnitude=1.0,
        max_magnitude=20.0,
        default_unit="quarters",
        default_path="Scenario persistence window",
        supported_directions=frozenset({"flat"}),
        scenario_packs=frozenset({"cre", "oil"}),
    ),
    "office_occupancy": FactorDefinition(
        factor_id="office_occupancy",
        label="Office occupancy",
        units=frozenset({"percent"}),
        min_magnitude=0.0,
        max_magnitude=80.0,
        default_unit="percent",
        default_path="Occupancy -> rental cash flow -> borrower stress",
        supported_directions=frozenset({"down"}),
        scenario_packs=frozenset({"cre"}),
    ),
    "credit_availability": FactorDefinition(
        factor_id="credit_availability",
        label="Credit availability",
        units=frozenset({"percent"}),
        min_magnitude=0.0,
        max_magnitude=80.0,
        default_unit="percent",
        default_path="Bank lending capacity -> downstream borrowers",
        supported_directions=frozenset({"down"}),
        scenario_packs=frozenset({"cre"}),
    ),
    "oil_price": FactorDefinition(
        factor_id="oil_price",
        label="Oil price",
        units=frozenset({"usd_per_barrel"}),
        min_magnitude=1.0,
        max_magnitude=250.0,
        default_unit="usd_per_barrel",
        default_path="Oil price -> energy producers -> fuel-intensive sectors",
        supported_directions=frozenset({"up", "down"}),
        scenario_packs=frozenset({"oil"}),
    ),
    "jet_fuel_cost": FactorDefinition(
        factor_id="jet_fuel_cost",
        label="Jet fuel cost",
        units=frozenset({"percent"}),
        min_magnitude=0.0,
        max_magnitude=150.0,
        default_unit="percent",
        default_path="Fuel cost -> airlines -> travel and logistics margins",
        supported_directions=frozenset({"up", "down"}),
        scenario_packs=frozenset({"oil"}),
    ),
    "transport_margin": FactorDefinition(
        factor_id="transport_margin",
        label="Transport margin",
        units=frozenset({"percent"}),
        min_magnitude=0.0,
        max_magnitude=80.0,
        default_unit="percent",
        default_path="Operating margin -> logistics credit quality",
        supported_directions=frozenset({"down"}),
        scenario_packs=frozenset({"oil"}),
    ),
}


PROMPT_VERSION = "shock-parse-v1"
GEMINI_PRO_MODEL_ALIAS = "gemini-pro-shock-parser"

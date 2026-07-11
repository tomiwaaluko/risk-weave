"""Shock parsing boundary for Gemini Pro structured output.

`RW-AI-003` requires Pro-tier shock parsing. This module keeps the product
boundary explicit: the Gemini output shape is strict JSON, then deterministic
validation decides whether the scenario may execute (`RW-SEC-003`).
"""

from __future__ import annotations

import re
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from riskweave.scenario.catalog import GEMINI_PRO_MODEL_ALIAS, PROMPT_VERSION, SUPPORTED_FACTORS
from riskweave.scenario.models import (
    Assumption,
    AssumptionKind,
    Direction,
    ParsedScenario,
    ScenarioFactor,
    ScenarioStatus,
)
from riskweave.scenario.validation import validate_scenario

PROMPT_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "tool execution",
    "call tool",
)


def _scenario_id(text: str) -> str:
    return f"scn-{uuid5(NAMESPACE_URL, text.strip().lower())}"


def _number_before(text: str, tokens: tuple[str, ...]) -> float | None:
    for token in tokens:
        match = re.search(rf"(\d+(?:\.\d+)?)\s*{token}", text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _factor(
    factor_id: str,
    direction: Direction,
    magnitude: float,
    unit: str | None = None,
    horizon: str = "6 quarters",
    as_of_date: date = date(2026, 7, 11),
    confidence: float = 0.88,
) -> ScenarioFactor:
    definition = SUPPORTED_FACTORS[factor_id]
    return ScenarioFactor(
        factor_id=factor_id,
        label=definition.label,
        direction=direction,
        magnitude=magnitude,
        unit=unit or definition.default_unit,
        as_of_date=as_of_date,
        horizon=horizon,
        shock_path=definition.default_path,
        geography="United States",
        sector_scope=", ".join(sorted(definition.scenario_packs)),
        parsing_confidence=confidence,
    )


def _extract_horizon(text: str) -> str:
    quarters = _number_before(text, ("quarter", "quarters"))
    if quarters is not None:
        return f"{int(quarters)} quarters"
    months = _number_before(text, ("month", "months"))
    if months is not None:
        return f"{int(months)} months"
    return "6 quarters"


def _deterministic_demo_parse(
    text: str,
) -> tuple[str, list[ScenarioFactor], list[Assumption], list[str]]:
    normalized = text.lower()
    horizon = _extract_horizon(text)
    factors: list[ScenarioFactor] = []
    assumptions: list[Assumption] = [
        Assumption(
            kind=AssumptionKind.AI_INFERRED,
            text="Scenario geography defaults to United States.",
        ),
    ]
    missing: list[str] = []

    if any(marker in normalized for marker in PROMPT_INJECTION_MARKERS):
        missing.append("Prompt-injection text was treated as untrusted scenario text.")

    if any(
        term in normalized for term in ("commercial real-estate", "commercial real estate", "cre")
    ):
        pack = "cre"
        value = _number_before(text, ("%", "percent")) or 20.0
        rate = _number_before(text, ("basis points", "bps")) or 150.0
        factors.extend(
            [
                _factor("cre_property_value", Direction.DOWN, value, horizon=horizon),
                _factor("refinancing_rate", Direction.UP, rate, horizon=horizon),
                _factor(
                    "stress_duration",
                    Direction.FLAT,
                    float(horizon.split()[0]),
                    horizon=horizon,
                ),
                _factor("office_occupancy", Direction.DOWN, 12.0, horizon=horizon, confidence=0.74),
                _factor(
                    "credit_availability",
                    Direction.DOWN,
                    8.0,
                    horizon=horizon,
                    confidence=0.72,
                ),
            ]
        )
        assumptions.append(
            Assumption(
                kind=AssumptionKind.DEFAULT,
                text=(
                    "Office occupancy and credit availability defaults keep "
                    "the CRE pack at five factors."
                ),
            )
        )
    elif "oil" in normalized or "brent" in normalized or "wti" in normalized:
        pack = "oil"
        oil = _number_before(text, ("dollar", "usd", "\\$")) or 140.0
        factors.extend(
            [
                _factor("oil_price", Direction.UP, oil, horizon=horizon),
                _factor("jet_fuel_cost", Direction.UP, 35.0, horizon=horizon, confidence=0.76),
                _factor("transport_margin", Direction.DOWN, 10.0, horizon=horizon, confidence=0.76),
                _factor("refinancing_rate", Direction.UP, 50.0, horizon=horizon, confidence=0.70),
                _factor(
                    "stress_duration",
                    Direction.FLAT,
                    float(horizon.split()[0]),
                    horizon=horizon,
                ),
            ]
        )
        assumptions.append(
            Assumption(
                kind=AssumptionKind.DEFAULT,
                text=(
                    "Oil template adds fuel, margin, rates, and duration factors for demo coverage."
                ),
            )
        )
    else:
        pack = "unsupported"
        words = re.sub(r"[^a-zA-Z0-9_ -]", "", text).strip()[:40] or "unknown"
        factors.append(
            ScenarioFactor(
                factor_id=f"unsupported:{words}",
                label="Unsupported shock factor",
                direction=Direction.AMBIGUOUS,
                magnitude=0.0,
                unit="unknown",
                as_of_date=date(2026, 7, 11),
                horizon="",
                shock_path="Unsupported user-provided shock",
                geography="Unresolved",
                sector_scope="Unresolved",
                parsing_confidence=0.15,
            )
        )
        missing.append("No supported CRE or oil shock factor could be mapped from the input.")
        assumptions.append(
            Assumption(kind=AssumptionKind.UNRESOLVED, text="Supported factor id is unresolved.")
        )

    return pack, factors, assumptions, missing


def parse_shock_text(text: str) -> ParsedScenario:
    """Parse untrusted user text into a reviewable scenario.

    The current implementation uses deterministic demo parsing while preserving
    the Gemini strict-output boundary fields (`prompt_version`, model alias,
    confidence) expected by the API. It never executes tools from user text.
    """

    clean_text = text.strip()
    if not clean_text:
        clean_text = "unsupported empty shock"

    pack, factors, assumptions, missing = _deterministic_demo_parse(clean_text)
    provisional = ParsedScenario(
        scenario_id=_scenario_id(clean_text),
        original_text=clean_text,
        scenario_pack=pack,
        factors=tuple(factors),
        assumptions=tuple(assumptions),
        missing_information=tuple(missing),
        prompt_version=PROMPT_VERSION,
        model_alias=GEMINI_PRO_MODEL_ALIAS,
        parsing_confidence=min((factor.parsing_confidence for factor in factors), default=0.0),
        status=ScenarioStatus.DRAFT,
        validation={"status": ScenarioStatus.DRAFT, "issues": ()},
    )
    validation = validate_scenario(provisional)
    return provisional.model_copy(update={"validation": validation, "status": validation.status})

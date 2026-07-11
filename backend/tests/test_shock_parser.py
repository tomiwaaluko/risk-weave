"""Hermetic tests for the RIS-18 live-Gemini shock parser.

These use a fake transport so no real Gemini call happens. They pin the
non-negotiable invariants of the reduced scope:

* Gemini only *finds* the sentence; a magnitude it does not echo verbatim is
  rejected (RW-AI-010 / RW-ALG-001).
* A schema-invalid, non-verbatim, or non-READY response retries once then falls
  back to the committed pre-parse (no white-screen).
"""

from __future__ import annotations

import json

import pytest

from riskweave.scenario.catalog import GEMINI_PRO_MODEL_ALIAS, PROMPT_VERSION, SUPPORTED_FACTORS
from riskweave.scenario.models import ScenarioStatus
from riskweave.scenario.presets import get_preset
from riskweave_api.extraction.gemini import GeminiResponseError
from riskweave_api.extraction.shock_parser import (
    FactorIdEnum,
    GeminiShockParser,
    UnitEnum,
    shock_parse_response_schema,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeTransport:
    """Returns canned ``output_text`` values, one per ``create_interaction`` call."""

    def __init__(self, *outputs: str | Exception) -> None:
        self._outputs = list(outputs)
        self.calls: list[dict[str, object]] = []

    def create_interaction(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        result = self._outputs.pop(0)
        if isinstance(result, Exception):
            raise result
        return {"output_text": result, "usage": {}}


def _cre_payload() -> str:
    return json.dumps(
        {
            "scenario_pack": "cre",
            "factors": [
                {
                    "factor_id": "cre_property_value",
                    "direction": "down",
                    "magnitude": 20,
                    "unit": "percent",
                    "horizon": "six quarters",
                    "geography": "United States",
                    "sector_scope": "cre",
                    "source_quote": "Commercial real-estate values fall 20%",
                },
                {
                    "factor_id": "refinancing_rate",
                    "direction": "up",
                    "magnitude": 150,
                    "unit": "basis_points",
                    "horizon": "six quarters",
                    "geography": "United States",
                    "sector_scope": "cre",
                    "source_quote": "refinancing rates rise 150 basis points",
                },
            ],
        }
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_parses_preset_via_live_transport_into_ready_scenario():
    transport = FakeTransport(_cre_payload())
    parser = GeminiShockParser(transport)

    result = parser.parse_preset(get_preset("cre"))

    assert result.source == "gemini"
    assert result.attempts == 1
    assert result.model_alias == GEMINI_PRO_MODEL_ALIAS
    assert result.prompt_version == PROMPT_VERSION
    scenario = result.scenario
    assert scenario.status is ScenarioStatus.READY
    assert scenario.scenario_id == "preset-cre"
    assert [f.factor_id for f in scenario.factors] == [
        "cre_property_value",
        "refinancing_rate",
    ]


def test_transport_called_with_pro_model_temperature_zero_and_strict_schema():
    transport = FakeTransport(_cre_payload())
    parser = GeminiShockParser(transport)

    parser.parse_preset(get_preset("cre"))

    call = transport.calls[0]
    assert call["temperature"] == 0
    assert "pro" in str(call["model"]).lower()
    response_format = call["response_format"]
    assert response_format["mime_type"] == "application/json"
    assert response_format["schema"] == shock_parse_response_schema()


def test_magnitudes_are_echoed_verbatim_not_altered():
    transport = FakeTransport(_cre_payload())
    parser = GeminiShockParser(transport)

    scenario = parser.parse_preset(get_preset("cre")).scenario

    magnitudes = {f.factor_id: f.magnitude for f in scenario.factors}
    assert magnitudes["cre_property_value"] == 20
    assert magnitudes["refinancing_rate"] == 150


# ---------------------------------------------------------------------------
# Invariant: Gemini may not invent a magnitude
# ---------------------------------------------------------------------------


def test_falls_back_when_magnitude_is_not_verbatim_in_source():
    invented = json.dumps(
        {
            "scenario_pack": "cre",
            "factors": [
                {
                    "factor_id": "cre_property_value",
                    "direction": "down",
                    # 37 never appears in the preset sentence: this is invention.
                    "magnitude": 37,
                    "unit": "percent",
                    "horizon": "six quarters",
                    "geography": "United States",
                    "sector_scope": "cre",
                    "source_quote": "Commercial real-estate values fall 20%",
                }
            ],
        }
    )
    # Same invented output on the retry too, so the parser must fall back.
    transport = FakeTransport(invented, invented)
    parser = GeminiShockParser(transport)

    result = parser.parse_preset(get_preset("cre"))

    assert result.source == "fallback"
    assert result.fallback_reason is not None
    assert "verbatim" in result.fallback_reason
    # The committed pre-parse is still READY, so the demo never white-screens.
    assert result.scenario.status is ScenarioStatus.READY
    assert len(transport.calls) == 2


def test_falls_back_when_source_quote_is_fabricated():
    fabricated = json.dumps(
        {
            "scenario_pack": "cre",
            "factors": [
                {
                    "factor_id": "cre_property_value",
                    "direction": "down",
                    "magnitude": 20,
                    "unit": "percent",
                    "horizon": "six quarters",
                    "geography": "United States",
                    "sector_scope": "cre",
                    # Quote text that is not a substring of the preset sentence.
                    "source_quote": "values collapse by 20 percent overnight",
                }
            ],
        }
    )
    transport = FakeTransport(fabricated, fabricated)
    parser = GeminiShockParser(transport)

    result = parser.parse_preset(get_preset("cre"))

    assert result.source == "fallback"
    assert result.scenario.status is ScenarioStatus.READY


# ---------------------------------------------------------------------------
# Retry + fallback behavior
# ---------------------------------------------------------------------------


def test_retries_once_then_succeeds_on_second_attempt():
    transport = FakeTransport("not json at all", _cre_payload())
    parser = GeminiShockParser(transport)

    result = parser.parse_preset(get_preset("cre"))

    assert result.source == "gemini"
    assert result.attempts == 2
    assert len(transport.calls) == 2


def test_falls_back_after_two_schema_invalid_responses():
    transport = FakeTransport("garbage", "still garbage")
    parser = GeminiShockParser(transport)

    result = parser.parse_preset(get_preset("cre"))

    assert result.source == "fallback"
    assert result.scenario.status is ScenarioStatus.READY
    assert len(transport.calls) == 2


def test_falls_back_when_transport_raises_response_error():
    error = GeminiResponseError("Gemini API request failed", 1, [])
    transport = FakeTransport(error, error)
    parser = GeminiShockParser(transport)

    result = parser.parse_preset(get_preset("cre"))

    assert result.source == "fallback"
    assert result.scenario.status is ScenarioStatus.READY


def test_falls_back_when_validation_rejects_the_parse():
    # Direction "up" is unsupported for cre_property_value -> validation INVALID.
    bad_direction = json.dumps(
        {
            "scenario_pack": "cre",
            "factors": [
                {
                    "factor_id": "cre_property_value",
                    "direction": "up",
                    "magnitude": 20,
                    "unit": "percent",
                    "horizon": "six quarters",
                    "geography": "United States",
                    "sector_scope": "cre",
                    "source_quote": "Commercial real-estate values fall 20%",
                }
            ],
        }
    )
    transport = FakeTransport(bad_direction, bad_direction)
    parser = GeminiShockParser(transport)

    result = parser.parse_preset(get_preset("cre"))

    assert result.source == "fallback"
    assert result.scenario.status is ScenarioStatus.READY


# ---------------------------------------------------------------------------
# Strict schema is catalog-driven (no drift)
# ---------------------------------------------------------------------------


def test_schema_enums_track_the_supported_factor_catalog():
    assert {member.value for member in FactorIdEnum} == set(SUPPORTED_FACTORS)
    allowed_units = {unit for d in SUPPORTED_FACTORS.values() for unit in d.units}
    assert {member.value for member in UnitEnum} == allowed_units


def test_response_schema_is_strict_json_schema():
    schema = shock_parse_response_schema()
    assert schema["additionalProperties"] is False
    assert "factors" in schema["properties"]


@pytest.mark.parametrize("preset_id", ["cre", "oil"])
def test_every_preset_has_a_ready_fallback(preset_id):
    # A transport that always fails forces the committed fallback for each preset.
    transport = FakeTransport("garbage", "garbage")
    parser = GeminiShockParser(transport)

    result = parser.parse_preset(get_preset(preset_id))

    assert result.source == "fallback"
    assert result.scenario.status is ScenarioStatus.READY
    assert result.scenario.factors

"""Gated live smoke tests for the shared Gemini client (RIS-24).

These call the real Gemini API. They are deselected by default (see the
``-m 'not live_gemini'`` addopts) and additionally skip when no real
``GEMINI_API_KEY`` is available, so CI and a bare ``uv run pytest`` stay
hermetic. Run explicitly with::

    uv run pytest -m live_gemini

The key is resolved from the environment first, then the repo-root ``.env``
(never committed), so the command above works with the key stored in ``.env``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from riskweave.scenario.models import ScenarioStatus
from riskweave.scenario.presets import get_preset
from riskweave_api.extraction.gemini import (
    GEMINI_PARSING_MODEL,
    GeminiExtractionClient,
    GeminiRestTransport,
)
from riskweave_api.extraction.schemas import (
    CovenantThresholdExtractionBatch,
    RelationshipExtractionBatch,
)
from riskweave_api.extraction.shock_parser import GeminiShockParser

pytestmark = pytest.mark.live_gemini

# A representative real 10-K credit-facility disclosure. Explicit and unambiguous
# so a temperature-0 extraction is stable across runs.
_RELATIONSHIP_CHUNK = (
    "During fiscal 2024, the Company maintained a $500 million senior secured revolving "
    "credit facility with Wells Fargo Bank, National Association, as administrative agent. "
    "As of December 31, 2024, borrowings of $220 million were outstanding under the facility."
)

_COVENANT_CHUNK = (
    "The credit agreement requires the Company to maintain a consolidated total net leverage "
    "ratio not to exceed 4.00 to 1.00 and a minimum interest coverage ratio of 2.50 to 1.00, "
    "tested quarterly."
)

_DEMO_SHOCK_SENTENCE = "Commercial real estate values decline 30% over the next twelve months."

_SOURCE_DOCUMENT_ID = "0000000001-24-000001"


def _resolve_live_key() -> SecretStr | None:
    raw = os.environ.get("GEMINI_API_KEY")
    if not raw:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("GEMINI_API_KEY="):
                    raw = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not raw or raw.startswith("replace-with"):
        return None
    return SecretStr(raw)


@pytest.fixture
def live_key() -> SecretStr:
    key = _resolve_live_key()
    if key is None:
        pytest.skip("no real GEMINI_API_KEY available; live Gemini smoke tests skipped")
    return key


@pytest.fixture
def live_client(live_key: SecretStr) -> GeminiExtractionClient:
    return GeminiExtractionClient(GeminiRestTransport(live_key), api_key=live_key)


def test_live_relationship_extraction_returns_schema_valid_json(
    live_client: GeminiExtractionClient,
) -> None:
    response = live_client.extract_relationships(_RELATIONSHIP_CHUNK, _SOURCE_DOCUMENT_ID, 0)

    assert isinstance(response.payload, RelationshipExtractionBatch)
    assert response.payload.relationships, "expected at least one disclosed relationship"
    for relationship in response.payload.relationships:
        # Provenance is mandatory (RW-ALG-032): every relationship carries its passage.
        assert relationship.source_passage
        assert relationship.passage_location.source_document_id == _SOURCE_DOCUMENT_ID


def test_live_covenant_extraction_returns_schema_valid_json(
    live_client: GeminiExtractionClient,
) -> None:
    response = live_client.extract_covenants(_COVENANT_CHUNK, _SOURCE_DOCUMENT_ID, 0)

    assert isinstance(response.payload, CovenantThresholdExtractionBatch)
    assert response.payload.covenants, "expected at least one disclosed covenant threshold"
    covenant_types = {covenant.covenant_type for covenant in response.payload.covenants}
    assert covenant_types <= {
        "leverage_limit",
        "interest_coverage_minimum",
        "minimum_liquidity",
    }


def test_live_pro_tier_structured_parse_of_demo_shock_sentence(live_key: SecretStr) -> None:
    # The Pro tier (RW-AI-003) is exercised directly via the shared transport; the full
    # RIS-18 shock-parsing client is out of scope for this ticket.
    shock_schema = {
        "type": "object",
        "properties": {
            "shock_type": {"type": "string"},
            "target_sector": {"type": "string"},
            "magnitude_text": {"type": "string"},
            "direction": {"type": "string", "enum": ["increase", "decline"]},
        },
        "required": ["shock_type", "target_sector", "magnitude_text", "direction"],
        "additionalProperties": False,
    }
    transport = GeminiRestTransport(live_key)

    response = transport.create_interaction(
        model=GEMINI_PARSING_MODEL,
        input=(
            "Parse this financial shock into the schema. Quote the magnitude verbatim.\n\n"
            f"Shock: {_DEMO_SHOCK_SENTENCE}"
        ),
        temperature=0,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": shock_schema,
        },
    )

    parsed = json.loads(str(response["output_text"]))
    assert set(parsed) == {"shock_type", "target_sector", "magnitude_text", "direction"}
    assert parsed["direction"] == "decline"
    assert "30" in parsed["magnitude_text"]


@pytest.mark.parametrize("preset_id", ["cre", "oil"])
def test_live_shock_parser_parses_preset_from_real_gemini(
    live_key: SecretStr, preset_id: str
) -> None:
    # RIS-18: the preset parse endpoint must actually exercise the live client,
    # not just a fake. Each trusted preset should round-trip through Gemini into a
    # READY scenario whose magnitudes are echoed verbatim from the sentence.
    parser = GeminiShockParser(GeminiRestTransport(live_key))

    result = parser.parse_preset(get_preset(preset_id))

    assert result.source == "gemini", f"expected live parse, got fallback: {result.fallback_reason}"
    assert result.scenario.status is ScenarioStatus.READY
    assert result.scenario.factors
    source_digits = result.scenario.original_text.replace(",", "")
    for factor in result.scenario.factors:
        magnitude = factor.magnitude
        token = str(int(magnitude)) if magnitude.is_integer() else str(magnitude)
        assert token in source_digits

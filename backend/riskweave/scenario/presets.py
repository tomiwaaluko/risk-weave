"""Preset shock prompts for the reduced RIS-18 demo path.

Two trusted preset sentences (CRE decline, oil price shock) are offered as
clickable prompts. Each is parsed by a real Gemini structured call
(:mod:`riskweave_api.extraction.shock_parser`). When that live call cannot
produce a verbatim-faithful, READY scenario, the committed deterministic
pre-parse below keeps the demo alive (the "no white-screen" guard).

The preset strings are trusted, so the freeform prompt-injection surface of the
full lifecycle is out of scope here; Gemini output is still treated as data.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from riskweave.scenario.models import ParsedScenario, ScenarioStatus
from riskweave.scenario.parser import parse_shock_text
from riskweave.scenario.templates import TEMPLATE_TEXTS
from riskweave.scenario.validation import validate_scenario


@dataclass(frozen=True)
class ShockPreset:
    """A trusted, clickable shock prompt surfaced in the reduced demo UI."""

    preset_id: str
    label: str
    prompt_text: str


PRESETS: tuple[ShockPreset, ...] = (
    ShockPreset(
        preset_id="cre",
        label="Commercial real-estate decline",
        prompt_text=TEMPLATE_TEXTS["cre"],
    ),
    ShockPreset(
        preset_id="oil",
        label="Oil price shock",
        prompt_text=TEMPLATE_TEXTS["oil"],
    ),
)

_PRESETS_BY_ID: dict[str, ShockPreset] = {preset.preset_id: preset for preset in PRESETS}


def list_presets() -> tuple[ShockPreset, ...]:
    """Return the ordered preset prompts offered to the user."""
    return PRESETS


def get_preset(preset_id: str) -> ShockPreset:
    try:
        return _PRESETS_BY_ID[preset_id]
    except KeyError as exc:
        raise KeyError(f"unknown preset id: {preset_id!r}") from exc


@cache
def preset_fallback(preset_id: str) -> ParsedScenario:
    """Committed deterministic pre-parse used when the live Gemini call fails.

    The reduced RIS-18 guard: a schema-invalid (or non-verbatim) Gemini
    response must never white-screen the demo, so we fall back to this
    reproducible parse of the same trusted preset sentence. The fallback is
    itself validated to READY so the "Run" path always has an executable
    scenario.
    """
    preset = get_preset(preset_id)
    scenario = parse_shock_text(preset.prompt_text)
    scenario = scenario.model_copy(update={"scenario_id": f"preset-{preset_id}"})
    validation = validate_scenario(scenario)
    if validation.status is not ScenarioStatus.READY:
        raise ValueError(f"preset {preset_id!r} fallback is not READY")
    return scenario.model_copy(update={"validation": validation, "status": ScenarioStatus.READY})

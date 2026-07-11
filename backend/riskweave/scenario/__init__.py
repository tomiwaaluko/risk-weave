"""Structured scenario parsing and validation for RiskWeave."""

from riskweave.scenario.models import (
    Assumption,
    AssumptionKind,
    Direction,
    ParsedScenario,
    ScenarioFactor,
    ScenarioStatus,
    ValidationIssue,
    ValidationIssueCode,
    ValidationResult,
)
from riskweave.scenario.parser import parse_shock_text
from riskweave.scenario.presets import (
    PRESETS,
    ShockPreset,
    get_preset,
    list_presets,
    preset_fallback,
)
from riskweave.scenario.templates import list_templates
from riskweave.scenario.validation import validate_scenario

__all__ = [
    "PRESETS",
    "Assumption",
    "AssumptionKind",
    "Direction",
    "ParsedScenario",
    "ScenarioFactor",
    "ScenarioStatus",
    "ShockPreset",
    "ValidationIssue",
    "ValidationIssueCode",
    "ValidationResult",
    "get_preset",
    "list_presets",
    "list_templates",
    "parse_shock_text",
    "preset_fallback",
    "validate_scenario",
]

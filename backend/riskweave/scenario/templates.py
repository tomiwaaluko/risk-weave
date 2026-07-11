"""Prevalidated scenario templates for `RW-FR-002` and the demo exception."""

from __future__ import annotations

from riskweave.scenario.models import (
    Assumption,
    AssumptionKind,
    ParsedScenario,
    ScenarioStatus,
)
from riskweave.scenario.parser import parse_shock_text
from riskweave.scenario.validation import validate_scenario

TEMPLATE_TEXTS = {
    "cre": (
        "Commercial real-estate values fall 20%, refinancing rates rise "
        "150 basis points, stress persists six quarters."
    ),
    "oil": (
        "Oil rises to $140 per barrel for six quarters, pressuring "
        "fuel-intensive airlines and logistics margins."
    ),
}


def _template(template_id: str, text: str) -> ParsedScenario:
    scenario = parse_shock_text(text)
    assumptions = (
        *scenario.assumptions,
        Assumption(
            kind=AssumptionKind.SOURCE_DERIVED,
            text=f"Prevalidated demo template '{template_id}' is bound to the v1 scenario pack.",
        ),
    )
    scenario = scenario.model_copy(
        update={
            "scenario_id": f"template-{template_id}",
            "assumptions": assumptions,
            "prevalidated_template": True,
        }
    )
    validation = validate_scenario(scenario)
    if validation.status is not ScenarioStatus.READY:
        raise ValueError(f"template {template_id!r} is not prevalidated")
    return scenario.model_copy(update={"validation": validation, "status": ScenarioStatus.READY})


def list_templates() -> tuple[ParsedScenario, ParsedScenario]:
    return tuple(_template(template_id, text) for template_id, text in TEMPLATE_TEXTS.items())  # type: ignore[return-value]

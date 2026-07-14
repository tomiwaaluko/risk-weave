"""Complete validation rejection-class matrix for RIS-18 (`RW-FR-004`, `RW-FR-007`).

The acceptance criterion requires the validation engine test matrix to cover
*every* rejection class and to prove that an unvalidated scenario cannot reach
RUNNING. This module isolates one scenario per :class:`ValidationIssueCode`,
asserts each class is produced, and asserts the union of produced codes equals
the full enum -- so adding a new rejection class without a matrix case fails
this test rather than silently shipping uncovered.
"""

from __future__ import annotations

from datetime import date

import pytest

from riskweave.scenario.models import (
    Direction,
    ParsedScenario,
    ScenarioFactor,
    ScenarioStatus,
    ValidationIssueCode,
)
from riskweave.scenario.validation import validate_scenario

_VALID_DATE = date(2026, 7, 11)


def _factor(**overrides: object) -> ScenarioFactor:
    """A fully valid ``refinancing_rate`` factor with per-field overrides."""
    base: dict[str, object] = {
        "factor_id": "refinancing_rate",
        "label": "Refinancing rate",
        "direction": Direction.UP,
        "magnitude": 150.0,
        "unit": "basis_points",
        "as_of_date": _VALID_DATE,
        "horizon": "6 quarters",
        "shock_path": "Rates -> debt service -> refinancing stress",
        "geography": "United States",
        "sector_scope": "cre",
        "parsing_confidence": 0.9,
    }
    base.update(overrides)
    return ScenarioFactor(**base)  # type: ignore[arg-type]


def _scenario(*factors: ScenarioFactor) -> ParsedScenario:
    return ParsedScenario(
        scenario_id="matrix",
        original_text="validation matrix scenario",
        scenario_pack="cre",
        factors=tuple(factors),
        assumptions=(),
        missing_information=(),
        prompt_version="shock-parse-v1",
        model_alias="gemini-pro-shock-parser",
        parsing_confidence=0.9,
        status=ScenarioStatus.DRAFT,
        validation={"status": ScenarioStatus.DRAFT, "issues": ()},
    )


# One isolated scenario per rejection class. Each is built to produce *only* its
# target code so the matrix stays precise.
MATRIX: dict[ValidationIssueCode, ParsedScenario] = {
    ValidationIssueCode.MISSING_FACTOR: _scenario(),
    ValidationIssueCode.UNSUPPORTED_FACTOR: _scenario(
        _factor(factor_id="meme_token_liquidity", unit="percent")
    ),
    ValidationIssueCode.INVALID_UNIT: _scenario(_factor(unit="usd")),
    ValidationIssueCode.IMPOSSIBLE_DATE: _scenario(_factor(as_of_date=date(2050, 1, 1))),
    ValidationIssueCode.AMBIGUOUS_DIRECTION: _scenario(_factor(direction=Direction.AMBIGUOUS)),
    ValidationIssueCode.MISSING_HORIZON: _scenario(_factor(horizon="")),
    ValidationIssueCode.OUT_OF_BOUND_MAGNITUDE: _scenario(_factor(magnitude=9000.0)),
    # Same supported factor, conflicting directions (both individually valid).
    ValidationIssueCode.CONTRADICTION: _scenario(
        _factor(direction=Direction.UP),
        _factor(direction=Direction.DOWN),
    ),
}


@pytest.mark.parametrize(
    "code, scenario", list(MATRIX.items()), ids=lambda v: getattr(v, "value", "")
)
def test_each_rejection_class_is_produced_and_isolated(
    code: ValidationIssueCode, scenario: ParsedScenario
) -> None:
    result = validate_scenario(scenario)

    produced = {issue.code for issue in result.issues}
    assert code in produced, f"{code.value} was not produced by its matrix scenario"
    assert produced == {code}, (
        f"{code.value} scenario also produced {sorted(c.value for c in produced - {code})}"
    )
    # RW-FR-004: any rejection keeps the scenario out of READY, so it cannot run.
    assert result.status is ScenarioStatus.INVALID


def test_matrix_covers_every_rejection_class() -> None:
    """Fails if a ValidationIssueCode is added without a matrix case."""
    assert set(MATRIX) == set(ValidationIssueCode)


def test_fully_valid_scenario_reaches_ready() -> None:
    result = validate_scenario(_scenario(_factor()))

    assert result.issues == ()
    assert result.status is ScenarioStatus.READY

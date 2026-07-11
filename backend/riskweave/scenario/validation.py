"""Deterministic server-side scenario validation (`RW-FR-004`, `RW-FR-007`)."""

from __future__ import annotations

from datetime import date

from riskweave.scenario.catalog import SUPPORTED_FACTORS
from riskweave.scenario.models import (
    Direction,
    ParsedScenario,
    ScenarioStatus,
    ValidationIssue,
    ValidationIssueCode,
    ValidationResult,
)


def validate_scenario(scenario: ParsedScenario) -> ValidationResult:
    issues: list[ValidationIssue] = []
    seen_direction_by_factor: dict[str, Direction] = {}

    if not scenario.factors:
        issues.append(
            ValidationIssue(
                code=ValidationIssueCode.MISSING_FACTOR,
                field="factors",
                message="Scenario must include at least one supported shock factor.",
            )
        )

    for index, factor in enumerate(scenario.factors):
        field_prefix = f"factors[{index}]"
        definition = SUPPORTED_FACTORS.get(factor.factor_id)
        if definition is None:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.UNSUPPORTED_FACTOR,
                    field=f"{field_prefix}.factor_id",
                    factor_id=factor.factor_id,
                    message=f"Unsupported factor '{factor.factor_id}' cannot be executed.",
                )
            )
            continue

        if factor.unit not in definition.units:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.INVALID_UNIT,
                    field=f"{field_prefix}.unit",
                    factor_id=factor.factor_id,
                    message=(
                        f"Unit '{factor.unit}' is invalid for {definition.label}; "
                        f"expected one of {sorted(definition.units)}."
                    ),
                )
            )

        if factor.direction is Direction.AMBIGUOUS or factor.direction not in {
            Direction(direction) for direction in definition.supported_directions
        }:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.AMBIGUOUS_DIRECTION,
                    field=f"{field_prefix}.direction",
                    factor_id=factor.factor_id,
                    message=f"Direction '{factor.direction}' is not valid for {definition.label}.",
                )
            )

        if not definition.min_magnitude <= factor.magnitude <= definition.max_magnitude:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.OUT_OF_BOUND_MAGNITUDE,
                    field=f"{field_prefix}.magnitude",
                    factor_id=factor.factor_id,
                    message=(
                        f"Magnitude {factor.magnitude:g} {factor.unit} is outside the "
                        f"supported range {definition.min_magnitude:g}.."
                        f"{definition.max_magnitude:g}."
                    ),
                )
            )

        if factor.as_of_date.year < 1970 or factor.as_of_date > date(2035, 12, 31):
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.IMPOSSIBLE_DATE,
                    field=f"{field_prefix}.as_of_date",
                    factor_id=factor.factor_id,
                    message="As-of/start date is outside the supported scenario window.",
                )
            )

        if not factor.horizon.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.MISSING_HORIZON,
                    field=f"{field_prefix}.horizon",
                    factor_id=factor.factor_id,
                    message="Scenario factor requires a horizon before execution.",
                )
            )

        previous_direction = seen_direction_by_factor.get(factor.factor_id)
        if previous_direction is not None and previous_direction is not factor.direction:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.CONTRADICTION,
                    field=f"{field_prefix}.direction",
                    factor_id=factor.factor_id,
                    message=(
                        f"Factor '{factor.factor_id}' appears with conflicting directions "
                        f"'{previous_direction}' and '{factor.direction}'."
                    ),
                )
            )
        seen_direction_by_factor[factor.factor_id] = factor.direction

    unresolved = [
        assumption for assumption in scenario.assumptions if assumption.kind.value == "unresolved"
    ]
    for assumption in unresolved:
        issues.append(
            ValidationIssue(
                code=ValidationIssueCode.MISSING_HORIZON,
                field="assumptions",
                message=(
                    f"Unresolved assumption must be resolved before execution: {assumption.text}"
                ),
            )
        )

    return ValidationResult(
        status=ScenarioStatus.READY if not issues else ScenarioStatus.INVALID,
        issues=tuple(issues),
    )

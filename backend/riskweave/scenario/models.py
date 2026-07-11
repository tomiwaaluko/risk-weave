"""Pydantic models for structured scenario review (`RW-FR-003`)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    AMBIGUOUS = "ambiguous"


class ScenarioStatus(StrEnum):
    DRAFT = "DRAFT"
    INVALID = "INVALID"
    READY = "READY"


class AssumptionKind(StrEnum):
    USER = "user"
    SOURCE_DERIVED = "source_derived"
    DEFAULT = "default"
    AI_INFERRED = "ai_inferred"
    UNRESOLVED = "unresolved"


class ValidationIssueCode(StrEnum):
    UNSUPPORTED_FACTOR = "unsupported_factor"
    INVALID_UNIT = "invalid_unit"
    IMPOSSIBLE_DATE = "impossible_date"
    AMBIGUOUS_DIRECTION = "ambiguous_direction"
    MISSING_HORIZON = "missing_horizon"
    CONTRADICTION = "contradiction"
    OUT_OF_BOUND_MAGNITUDE = "out_of_bound_magnitude"
    MISSING_FACTOR = "missing_factor"


class Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AssumptionKind
    text: str = Field(min_length=1)


class ScenarioFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    direction: Direction
    magnitude: float
    unit: str = Field(min_length=1)
    as_of_date: date
    horizon: str
    shock_path: str = Field(min_length=1)
    geography: str = Field(min_length=1)
    sector_scope: str = Field(min_length=1)
    parsing_confidence: float = Field(ge=0.0, le=1.0)


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ValidationIssueCode
    field: str
    message: str
    factor_id: str | None = None


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ScenarioStatus
    issues: tuple[ValidationIssue, ...]


class ParsedScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    original_text: str = Field(min_length=1)
    scenario_pack: str = Field(min_length=1)
    factors: tuple[ScenarioFactor, ...]
    assumptions: tuple[Assumption, ...]
    missing_information: tuple[str, ...]
    prompt_version: str
    model_alias: str
    parsing_confidence: float = Field(ge=0.0, le=1.0)
    status: ScenarioStatus
    validation: ValidationResult
    prevalidated_template: bool = False

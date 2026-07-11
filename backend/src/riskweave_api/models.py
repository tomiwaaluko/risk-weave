from enum import StrEnum

from pydantic import BaseModel, Field


class ScenarioState(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ShockFactorIn(BaseModel):
    factor_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    magnitude: float


class ScenarioCreateRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    factors: list[ShockFactorIn] = Field(min_length=1)
    seed: int = 0


class ScenarioRunRequest(BaseModel):
    severity: float = Field(default=1.0, ge=0.0, le=2.0)

"""Pydantic v2 request/response models for RIS-14 (RW-FR-009, RW-FR-015, RW-FR-020)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Scenario lifecycle
# ---------------------------------------------------------------------------


class ScenarioState(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Valid forward transitions (RW-FR-009)
_VALID_TRANSITIONS: dict[ScenarioState, set[ScenarioState]] = {
    ScenarioState.DRAFT: {ScenarioState.VALIDATING, ScenarioState.CANCELLED},
    ScenarioState.VALIDATING: {ScenarioState.READY, ScenarioState.FAILED},
    ScenarioState.READY: {ScenarioState.QUEUED, ScenarioState.CANCELLED},
    ScenarioState.QUEUED: {ScenarioState.RUNNING, ScenarioState.CANCELLED},
    ScenarioState.RUNNING: {ScenarioState.COMPLETED, ScenarioState.PARTIAL, ScenarioState.FAILED},
    # Terminal states
    ScenarioState.COMPLETED: set(),
    ScenarioState.PARTIAL: set(),
    ScenarioState.FAILED: set(),
    ScenarioState.CANCELLED: set(),
}


def validate_transition(current: ScenarioState, next_state: ScenarioState) -> None:
    if next_state not in _VALID_TRANSITIONS[current]:
        raise ValueError(f"Invalid transition {current} → {next_state}")


class ShockFactorIn(BaseModel):
    factor_id: str
    node_id: str
    magnitude: float = Field(..., description="Normalized signed magnitude; Gemini never sets this")

    @field_validator("factor_id", "node_id")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v


class ScenarioCreateRequest(BaseModel):
    scenario_id: str
    snapshot_id: str
    graph_version: str
    factors: list[ShockFactorIn] = Field(..., min_length=1)
    seed: int = 0
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scenario_id", "snapshot_id", "graph_version")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v


class ScenarioRecord(BaseModel):
    scenario_id: str
    snapshot_id: str
    graph_version: str
    engine_version: str
    seed: int
    config: dict[str, Any]
    state: ScenarioState


class RunRequest(BaseModel):
    severity: float = Field(default=1.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Propagation results
# ---------------------------------------------------------------------------


class PathContributionOut(BaseModel):
    path_key: str
    factor_id: str
    hop_count: int
    contribution: float
    edge_ids: list[str]
    method_ids: list[str]
    provenance_refs: list[str]


class NodeImpactOut(BaseModel):
    node_id: str
    raw_impact: float
    risk_score: float
    contributions: list[PathContributionOut]


class RunResult(BaseModel):
    scenario_id: str
    snapshot_id: str
    graph_version: str
    engine_version: str
    seed: int
    severity: float
    damping: float
    floor: float
    max_hops: int
    impacts: dict[str, NodeImpactOut]
    ranked_entity_ids: list[str]
    latency_ms: float


# ---------------------------------------------------------------------------
# Evidence-bound explanations (RIS-19, RW-AI-011)
# ---------------------------------------------------------------------------


class CitationOut(BaseModel):
    """One provenance record an explanation cites (`RW-ALG-032`)."""

    citation_id: str
    edge_id: str
    source_name: str
    target_name: str
    relationship_type: str
    method_id: str
    source_document_id: str
    source_passage: str
    char_start: int
    char_end: int
    filing_date: str
    data_timestamp: str
    extraction_confidence: float


class StructuredNumberOut(BaseModel):
    """One labeled verified figure for the guard-failure fallback."""

    label: str
    value: float
    citation_ids: list[str] = Field(default_factory=list)


class ExplanationOut(BaseModel):
    """A guarded, evidence-bound explanation of one node's scenario impact.

    ``prose`` is present only when the generated text passed the numeric guard
    (`RW-AI-011`). When it failed after one regeneration, ``used_fallback`` is
    True, ``prose`` is null, and ``structured_numbers`` carries the labeled
    verified figures shown instead — the rejected prose is never returned.
    """

    node_id: str
    node_name: str
    audience: str
    prose: str | None
    used_fallback: bool
    attempts: int
    guard_violations: list[str]
    citations: list[CitationOut]
    structured_numbers: list[StructuredNumberOut]
    model: str


# ---------------------------------------------------------------------------
# Run-scoped Q&A (RIS-19, RW-FR-024, RW-AI-002)
# ---------------------------------------------------------------------------


class QaRequest(BaseModel):
    """A run-scoped question about a completed scenario run."""

    question: str = Field(..., min_length=1)
    severity: float = Field(default=1.0, ge=0.0, le=1.0)
    audience: str = "analyst"


class ToolCallAuditOut(BaseModel):
    """One entry of the per-session tool-call audit log (`RW-FR-024`).

    ``status`` is ``ok`` for an executed §13.2 tool, or ``unknown_tool`` /
    ``invalid_args`` for a call refused server-side (`RW-SEC-002`).
    """

    tool_name: str
    args: dict[str, Any]
    result_hash: str
    status: str
    timestamp: str


class QaAnswerOut(BaseModel):
    """A guarded run-scoped Q&A answer, or an explicit withholding.

    ``answer`` is present only when the generated text passed the same numeric
    containment + citation guard as explanations (`RW-AI-011`). When it could not
    be grounded, ``withheld`` is True, ``answer`` is null, and ``reason`` /
    ``guard_violations`` explain why — the unsupported prose is never returned.
    ``audit`` captures every tool call (executed or refused) for the session.
    """

    session_id: str
    question: str
    audience: str
    answer: str | None
    withheld: bool
    reason: str | None
    citations: list[CitationOut]
    audit: list[ToolCallAuditOut]
    tool_call_count: int
    answer_attempts: int
    guard_violations: list[str]
    model: str


# ---------------------------------------------------------------------------
# WebSocket messages
# ---------------------------------------------------------------------------


class SliderMessage(BaseModel):
    severity: float = Field(..., ge=0.0, le=1.0)


class SliderUpdate(BaseModel):
    severity: float
    impacts: dict[str, NodeImpactOut]
    ranked_entity_ids: list[str]
    cached: bool
    latency_ms: float


# ---------------------------------------------------------------------------
# §13.2 registry payloads
# ---------------------------------------------------------------------------


class ResolveEntityRequest(BaseModel):
    query: str


class ResolveEntityResponse(BaseModel):
    node_id: str | None
    name: str | None
    node_type: str | None


class CompanyExposuresResponse(BaseModel):
    node_id: str
    outgoing_edges: list[dict[str, Any]]


class PropagateShockResponse(BaseModel):
    result: RunResult


class PropagationPathsResponse(BaseModel):
    paths: list[PathContributionOut]


class RatioResponse(BaseModel):
    method_id: str
    value: float
    provenance_ref: str


class FilingPassageResponse(BaseModel):
    source_document_id: str
    passage: str
    char_start: int
    char_end: int


class FredSeriesResponse(BaseModel):
    series_id: str
    values: list[dict[str, Any]]

"""Evaluation-dashboard endpoint (RIS-21, `RW-OPS-001`, spec §15).

Serves the beat-6 "not a wrapper" report: the six §15 metric families computed
from committed fixtures and deterministic runs (see
:mod:`riskweave.evaluation.report`). Read-only and unauthenticated — it exposes
no secret and mutates nothing, and the demo build must render it.

Metrics are recomputed per request (all inputs are snapshot-pinned, so the
result is reproducible) and stamped with a server ``generated_at`` timestamp;
the pure core stays clock-free for testability.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from riskweave.evaluation.report import run_evaluation
from riskweave.graph.assembly import GraphAssemblyError

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


class MetricRowOut(BaseModel):
    key: str
    label: str
    family: str
    actual_display: str
    target_display: str
    passed: bool | None
    detail: str


class EvaluationReportOut(BaseModel):
    snapshot_id: str
    graph_version: str
    generated_at: str
    all_passed: bool
    families: list[str]
    rows: list[MetricRowOut]


@router.get(
    "/report",
    response_model=EvaluationReportOut,
    summary="Compute the §15 evaluation-dashboard report",
)
def evaluation_report() -> EvaluationReportOut:
    """Recompute and return the full evaluation report from the pinned snapshot."""
    generated_at = datetime.now(UTC).isoformat()
    try:
        report = run_evaluation(generated_at=generated_at)
    except (GraphAssemblyError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"evaluation inputs unavailable: {exc}",
        ) from exc
    return EvaluationReportOut(**report.to_dict())

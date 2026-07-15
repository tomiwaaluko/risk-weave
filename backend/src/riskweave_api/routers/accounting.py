"""Provider cost/quota accounting rollup endpoints (RIS-34, `RW-DATA-005`, §15).

Backs the RIS-21 evaluation dashboard's cost/usage panel: Gemini per-purpose
daily rollups and budget status, plus the most recent ingestion run's SEC/FRED
request counts against their documented fair-use ceilings. RIS-21's dashboard
shell has not landed yet, so this is exposed as its own small router the
dashboard page can call once it exists.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from riskweave_api.accounting.service import GeminiAccountingService
from riskweave_api.dependencies import get_accounting, get_accounting_session_factory
from riskweave_api.ingestion.models import IngestionRun
from riskweave_api.security import default_rate_limit

router = APIRouter(
    prefix="/accounting", tags=["accounting"], dependencies=[Depends(default_rate_limit)]
)


class GeminiRollupRow(BaseModel):
    day: date
    purpose: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class GeminiBudgetStatus(BaseModel):
    day: date
    spent_usd: float
    soft_threshold_usd: float
    hard_threshold_usd: float
    soft_breached: bool
    hard_breached: bool


class ProviderUsage(BaseModel):
    ingestion_run_id: int | None
    provider_usage: dict[str, object]


@router.get("/gemini/rollup", response_model=list[GeminiRollupRow])
def gemini_rollup(
    days: int = 7,
    accounting: GeminiAccountingService = Depends(get_accounting),
    session_factory=Depends(get_accounting_session_factory),
) -> list[GeminiRollupRow]:
    """Per-day/purpose/model Gemini token and cost totals for the last ``days`` days."""
    end = datetime.now(UTC).date()
    start = end - timedelta(days=max(0, days - 1))
    with session_factory() as session:
        rows = accounting.rollup(session, start=start, end=end)
    return [
        GeminiRollupRow(
            day=row.day,
            purpose=row.purpose,
            model=row.model,
            calls=row.calls,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cost_usd=float(row.cost_usd),
        )
        for row in rows
    ]


@router.get("/gemini/budget", response_model=GeminiBudgetStatus)
def gemini_budget(
    accounting: GeminiAccountingService = Depends(get_accounting),
    session_factory=Depends(get_accounting_session_factory),
) -> GeminiBudgetStatus:
    """Today's Gemini spend vs. the configured soft/hard daily budget thresholds."""
    with session_factory() as session:
        status = accounting.budget_status(session)
    return GeminiBudgetStatus(
        day=status.day,
        spent_usd=float(status.spent_usd),
        soft_threshold_usd=float(status.soft_threshold_usd),
        hard_threshold_usd=float(status.hard_threshold_usd),
        soft_breached=status.soft_breached,
        hard_breached=status.hard_breached,
    )


@router.get("/providers/latest", response_model=ProviderUsage)
def latest_provider_usage(
    session_factory=Depends(get_accounting_session_factory),
) -> ProviderUsage:
    """SEC/FRED request counts vs. documented fair-use limits from the latest ingestion run."""
    with session_factory() as session:
        run = session.scalar(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(1))
    if run is None:
        return ProviderUsage(ingestion_run_id=None, provider_usage={})
    return ProviderUsage(
        ingestion_run_id=run.id,
        provider_usage=(run.metadata_json or {}).get("provider_usage", {}),
    )

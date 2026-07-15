"""Gemini call accounting: per-call logging, daily rollups, budget gating (RIS-34)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from riskweave.accounting.pricing import estimate_cost_usd

from .models import GeminiUsageRecord

logger = logging.getLogger("riskweave_api.accounting")

# Purposes gated by the hard budget threshold: high-volume batch extraction is
# the only call site that can safely pause and resume (`_get_or_create_run`
# already skips completed chunks), so it is the only one refused when the hard
# threshold is breached. Interactive parse/explanation/Q&A stay open — the
# spec's decision priority ranks reliable demo behavior above cost.
BUDGET_GATED_PURPOSES = frozenset({"extraction"})


class BudgetExceededError(RuntimeError):
    """Raised when a budget-gated purpose would push spend past the hard cap."""


@dataclass(frozen=True)
class BudgetStatus:
    day: date
    spent_usd: Decimal
    soft_threshold_usd: Decimal
    hard_threshold_usd: Decimal

    @property
    def soft_breached(self) -> bool:
        return self.spent_usd >= self.soft_threshold_usd

    @property
    def hard_breached(self) -> bool:
        return self.spent_usd >= self.hard_threshold_usd


@dataclass(frozen=True)
class RollupRow:
    day: date
    purpose: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class GeminiAccountingService:
    def __init__(
        self,
        *,
        soft_daily_budget_usd: Decimal,
        hard_daily_budget_usd: Decimal,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.soft_daily_budget_usd = soft_daily_budget_usd
        self.hard_daily_budget_usd = hard_daily_budget_usd
        self._clock = clock

    def check_budget_or_raise(self, session: Session, *, purpose: str) -> BudgetStatus:
        """Raise :class:`BudgetExceededError` if a gated purpose has hit the hard cap.

        Non-gated purposes (parse/explanation/qa) still get a status back (and a
        soft-threshold warning logged) but are never blocked.
        """
        status = self.budget_status(session)
        if status.soft_breached:
            logger.warning(
                "Gemini daily soft budget threshold reached: spent=%s soft_threshold=%s day=%s",
                status.spent_usd,
                status.soft_threshold_usd,
                status.day,
            )
        if purpose in BUDGET_GATED_PURPOSES and status.hard_breached:
            raise BudgetExceededError(
                f"Gemini daily hard budget of ${status.hard_threshold_usd} reached "
                f"(spent ${status.spent_usd} on {status.day}); refusing further "
                f"{purpose!r} calls until tomorrow"
            )
        return status

    def budget_status(self, session: Session, *, today: date | None = None) -> BudgetStatus:
        day = today or self._clock().date()
        spent = self.daily_spend_usd(session, day)
        return BudgetStatus(
            day=day,
            spent_usd=spent,
            soft_threshold_usd=self.soft_daily_budget_usd,
            hard_threshold_usd=self.hard_daily_budget_usd,
        )

    def daily_spend_usd(self, session: Session, day: date) -> Decimal:
        total = session.scalar(
            select(func.coalesce(func.sum(GeminiUsageRecord.cost_usd), 0)).where(
                func.date(GeminiUsageRecord.created_at) == day.isoformat()
            )
        )
        return Decimal(total or 0)

    def record(
        self,
        session: Session,
        *,
        purpose: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> GeminiUsageRecord | None:
        """Log one Gemini call. Returns ``None`` (never raises) if tokens are unknown."""
        if input_tokens is None or output_tokens is None:
            logger.warning("skipping Gemini accounting for %s: token usage missing", purpose)
            return None
        record = GeminiUsageRecord(
            purpose=purpose,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
            created_at=self._clock(),
        )
        session.add(record)
        session.flush()
        return record

    def record_best_effort(
        self,
        session_factory: sessionmaker[Session],
        *,
        purpose: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        """Log a call in its own transaction, swallowing failures.

        Used from interactive request paths (explanation, Q&A) where an
        accounting hiccup must never break a demo response (reliable demo
        behavior outranks cost in the spec's decision priority, spec §0.4).
        """
        try:
            with session_factory() as session:
                self.record(
                    session,
                    purpose=purpose,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                session.commit()
        except Exception:
            logger.warning("Gemini accounting write failed for purpose=%s", purpose, exc_info=True)

    def rollup(self, session: Session, *, start: date, end: date) -> list[RollupRow]:
        """Per-day/purpose/model totals for ``start`` through ``end`` inclusive."""
        day_col = func.date(GeminiUsageRecord.created_at)
        rows = session.execute(
            select(
                day_col.label("day"),
                GeminiUsageRecord.purpose,
                GeminiUsageRecord.model,
                func.count().label("calls"),
                func.sum(GeminiUsageRecord.input_tokens).label("input_tokens"),
                func.sum(GeminiUsageRecord.output_tokens).label("output_tokens"),
                func.sum(GeminiUsageRecord.cost_usd).label("cost_usd"),
            )
            .where(day_col >= start.isoformat(), day_col <= end.isoformat())
            .group_by(day_col, GeminiUsageRecord.purpose, GeminiUsageRecord.model)
            .order_by(day_col)
        )
        return [
            RollupRow(
                day=date.fromisoformat(str(row.day)),
                purpose=row.purpose,
                model=row.model,
                calls=row.calls,
                input_tokens=int(row.input_tokens or 0),
                output_tokens=int(row.output_tokens or 0),
                cost_usd=Decimal(row.cost_usd or 0),
            )
            for row in rows
        ]

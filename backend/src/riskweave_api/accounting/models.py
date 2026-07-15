from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from riskweave_api.ingestion.models import Base


class GeminiUsageRecord(Base):
    """One accounted Gemini call: purpose, model, tokens, and computed cost.

    ``purpose`` is one of ``extraction`` / ``shock_parse`` / ``explanation`` /
    ``qa`` (RIS-34 scope) so rollups can break spend down by the tiering the
    spec expects (`RW-AI-003`): extraction on Flash, everything else on Pro.
    """

    __tablename__ = "gemini_usage_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[object] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

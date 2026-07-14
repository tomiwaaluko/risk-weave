"""SQLAlchemy models for scenario/run/graph-snapshot persistence (RIS-30).

Shares :class:`riskweave_api.ingestion.models.Base` so Alembic autogeneration
and migration history stay in one place across the ingestion and API layers.

Run rows are audit artifacts (`RW-NFR-001`, spec §21): once written they are
never mutated or deleted by normal application code, only appended to, so a
run can always be re-fetched and re-verified after a restart (`RW-FR-015`).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .ingestion.models import Base


class StoredGraphSnapshot(Base):
    __tablename__ = "stored_graph_snapshots"
    snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    graph_version: Mapped[str] = mapped_column(String(64))
    nodes_json: Mapped[list] = mapped_column(JSON)
    edges_json: Mapped[list] = mapped_column(JSON)
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StoredScenario(Base):
    __tablename__ = "stored_scenarios"
    scenario_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(128))
    graph_version: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(32))
    seed: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32))
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    factors_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScenarioRun(Base):
    """One persisted propagation run — an audit artifact, never mutated in place."""

    __tablename__ = "scenario_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("stored_scenarios.scenario_id"))
    snapshot_id: Mapped[str] = mapped_column(String(128))
    graph_version: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(32))
    seed: Mapped[int] = mapped_column(Integer)
    severity: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[float] = mapped_column(Float)
    result_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QaSession(Base):
    """One persisted run-scoped Q&A session — audit log for RW-FR-024."""

    __tablename__ = "qa_sessions"
    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    answer_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

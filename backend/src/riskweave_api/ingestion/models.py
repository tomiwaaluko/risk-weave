from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_document_id: Mapped[str] = mapped_column(String(64), unique=True)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    accession_number: Mapped[str] = mapped_column(String(32), unique=True)
    form: Mapped[str] = mapped_column(String(16))
    filing_date: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    canonical_text: Mapped[str] = mapped_column(Text)
    provider_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    normalization_map: Mapped[dict] = mapped_column(JSON, default=dict)
    chunks: Mapped[list[DocumentChunk]] = relationship(cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "char_start", "char_end"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    overlap_start: Mapped[int | None] = mapped_column(Integer)
    overlap_end: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))


class XbrlFact(Base):
    __tablename__ = "xbrl_facts"
    __table_args__ = (UniqueConstraint("identity_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String(64))
    cik: Mapped[str] = mapped_column(String(10), index=True)
    taxonomy: Mapped[str] = mapped_column(String(64))
    concept: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    accession_number: Mapped[str] = mapped_column(String(32))
    form: Mapped[str] = mapped_column(String(16))
    filed_date: Mapped[date] = mapped_column(Date)
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    fiscal_period: Mapped[str | None] = mapped_column(String(16))
    frame: Mapped[str | None] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))


class MacroSeries(Base):
    __tablename__ = "macro_series"
    series_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    units: Mapped[str] = mapped_column(String(128))
    frequency: Mapped[str] = mapped_column(String(128))
    source_release: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))


class MacroObservation(Base):
    __tablename__ = "macro_observations"
    __table_args__ = (UniqueConstraint("series_id", "observation_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("macro_series.series_id"))
    observation_date: Mapped[date] = mapped_column(Date)
    value: Mapped[object] = mapped_column(Numeric, nullable=True)
    realtime_start: Mapped[date] = mapped_column(Date)
    realtime_end: Mapped[date] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))


class DataSnapshot(Base):
    __tablename__ = "data_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    manifest_hash: Mapped[str] = mapped_column(String(64), unique=True)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest_json: Mapped[dict] = mapped_column(JSON, default=dict)


class SnapshotMember(Base):
    __tablename__ = "snapshot_members"
    __table_args__ = (UniqueConstraint("snapshot_id", "record_type", "record_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("data_snapshots.id"))
    record_type: Mapped[str] = mapped_column(String(32))
    record_id: Mapped[str] = mapped_column(String(128))
    content_hash: Mapped[str] = mapped_column(String(64))


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "chunk_id", "schema_name", "prompt_version", "model"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("data_snapshots.id"))
    chunk_id: Mapped[int] = mapped_column(ForeignKey("document_chunks.id"))
    schema_name: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    model_docs_checked_at: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer)
    input_token_count: Mapped[int | None] = mapped_column(Integer)
    output_token_count: Mapped[int | None] = mapped_column(Integer)
    outcome_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RelationshipExtraction(Base):
    __tablename__ = "relationship_extractions"
    __table_args__ = (UniqueConstraint("content_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("data_snapshots.id"))
    chunk_id: Mapped[int] = mapped_column(ForeignKey("document_chunks.id"))
    extraction_run_id: Mapped[int | None] = mapped_column(ForeignKey("extraction_runs.id"))
    source_entity: Mapped[str] = mapped_column(Text)
    target_entity: Mapped[str] = mapped_column(Text)
    relationship_type: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(16))
    disclosed_magnitude: Mapped[str | None] = mapped_column(Text)
    source_passage: Mapped[str] = mapped_column(Text)
    source_document_id: Mapped[str] = mapped_column(String(64))
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    extraction_confidence: Mapped[float] = mapped_column(Float)
    content_hash: Mapped[str] = mapped_column(String(64))
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CovenantThresholdExtraction(Base):
    __tablename__ = "covenant_threshold_extractions"
    __table_args__ = (UniqueConstraint("content_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("data_snapshots.id"))
    chunk_id: Mapped[int] = mapped_column(ForeignKey("document_chunks.id"))
    extraction_run_id: Mapped[int | None] = mapped_column(ForeignKey("extraction_runs.id"))
    entity: Mapped[str] = mapped_column(Text)
    covenant_type: Mapped[str] = mapped_column(String(64))
    threshold_value: Mapped[str] = mapped_column(Text)
    source_passage: Mapped[str] = mapped_column(Text)
    source_document_id: Mapped[str] = mapped_column(String(64))
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    extraction_confidence: Mapped[float] = mapped_column(Float)
    content_hash: Mapped[str] = mapped_column(String(64))
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

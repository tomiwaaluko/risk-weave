"""Reusable live-pipeline operations (RIS-28).

Shared by the ``pipeline_cli`` one-off runner and the guarded ``/admin/pipeline``
endpoints so both diagnose, extract, and build identically. Pure of any CLI or
HTTP concerns: functions take a session and return plain data / call a progress
callback.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from riskweave.graph.build_live import resolve_snapshot
from riskweave_api.extraction.gemini import GeminiExtractionClient, GeminiRestTransport
from riskweave_api.extraction.service import ExtractionService
from riskweave_api.ingestion.models import (
    Document,
    DocumentChunk,
    ExtractionRun,
    RelationshipExtraction,
    SnapshotMember,
)


def snapshot_chunk_ids(session: Session, snapshot_id: int) -> list[int]:
    """Ordered chunk ids belonging to a snapshot (mirrors ExtractionService)."""
    rows = session.execute(
        select(DocumentChunk.id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.accession_number.in_(
                select(SnapshotMember.record_id).where(
                    SnapshotMember.snapshot_id == snapshot_id,
                    SnapshotMember.record_type == "document",
                )
            )
        )
        .order_by(Document.accession_number, DocumentChunk.ordinal)
    )
    return [row[0] for row in rows]


def diagnose(session: Session, snapshot_id: int) -> dict:
    """Report snapshot + extraction counts (no Gemini calls)."""
    snapshot = resolve_snapshot(session, snapshot_id=snapshot_id)
    chunk_ids = snapshot_chunk_ids(session, snapshot.id)
    rel_total = session.scalar(select(func.count()).select_from(RelationshipExtraction))
    rel_for_snapshot = session.scalar(
        select(func.count())
        .select_from(RelationshipExtraction)
        .where(RelationshipExtraction.snapshot_id == snapshot.id)
    )
    run_rows = session.execute(
        select(ExtractionRun.status, func.count())
        .where(ExtractionRun.snapshot_id == snapshot.id)
        .group_by(ExtractionRun.status)
    ).all()
    return {
        "snapshot_id": snapshot.id,
        "snapshot_name": snapshot.name,
        "frozen_at": snapshot.frozen_at.isoformat() if snapshot.frozen_at else None,
        "chunks_in_snapshot": len(chunk_ids),
        "relationship_extractions_total": rel_total,
        "relationship_extractions_for_snapshot": rel_for_snapshot,
        "extraction_runs_by_status": {status: count for status, count in run_rows},
    }


logger = logging.getLogger("riskweave_api.pipeline")


@dataclass
class ExtractionProgress:
    """Mutable progress record for a running extraction pass."""

    snapshot_id: int
    total: int
    processed: int = 0
    inserted: int = 0
    skipped: int = 0
    failed: int = 0
    last_error: str | None = None

    def as_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "total": self.total,
            "processed": self.processed,
            "inserted": self.inserted,
            "skipped": self.skipped,
            "failed": self.failed,
            "last_error": self.last_error,
        }


def build_extraction_client(api_key: SecretStr) -> GeminiExtractionClient:
    return GeminiExtractionClient(GeminiRestTransport(api_key), api_key=api_key)


def run_extraction(
    session: Session,
    snapshot_id: int,
    *,
    api_key: SecretStr,
    limit: int | None = None,
    progress: Callable[[ExtractionProgress], None] | None = None,
) -> ExtractionProgress:
    """Run the Gemini relationship-extraction pass over a snapshot's chunks.

    Commits after every chunk so the run is durable and resumable (already
    completed per-chunk runs are skipped). Per-chunk failures are counted and the
    pass continues. ``progress`` is invoked after each chunk for live status.
    """
    snapshot = resolve_snapshot(session, snapshot_id=snapshot_id)
    chunk_ids = snapshot_chunk_ids(session, snapshot.id)
    if limit is not None:
        chunk_ids = chunk_ids[:limit]

    service = ExtractionService(session, build_extraction_client(api_key))
    state = ExtractionProgress(snapshot_id=snapshot.id, total=len(chunk_ids))
    for chunk_id in chunk_ids:
        try:
            result = service.extract_relationships_for_chunk(snapshot.id, chunk_id)
            state.inserted += result.inserted
            state.skipped += int(result.skipped_existing)
            session.commit()
        except Exception as exc:
            # A batch over tens of thousands of chunks must survive per-chunk
            # failures — a transient Gemini 503/timeout, a schema-invalid
            # response, an offset mismatch — without aborting the whole run.
            # The chunk is left un-``completed`` so a re-run retries it
            # (resumable); progress on prior chunks is already committed.
            session.rollback()
            state.failed += 1
            state.last_error = f"chunk {chunk_id}: {type(exc).__name__}: {exc}"
            logger.warning("extraction chunk %s failed: %s", chunk_id, exc)
        state.processed += 1
        if progress is not None:
            progress(state)
    return state

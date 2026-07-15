"""Run the live pipeline (extraction -> resolution -> derivation -> assembly).

RIS-28 operational entry point. Runs the RIS-10 Gemini extraction pass over a
frozen ingestion snapshot's chunks, then assembles the live graph (RIS-9/11/12)
from the stored relationships. Designed to run as a Railway one-off in the
``ingestion``/``backend`` image, where ``DATABASE_URL`` and ``GEMINI_API_KEY``
are present.

Subcommands (run from ``backend/``)::

    # cheap: print DB counts, no Gemini calls
    python -m riskweave_api.ingestion.pipeline_cli diagnose --snapshot-id 3

    # run extraction (resumable; already-completed chunks are skipped)
    python -m riskweave_api.ingestion.pipeline_cli extract --snapshot-id 3
    python -m riskweave_api.ingestion.pipeline_cli extract --snapshot-id 3 --limit 200

    # assemble + report the live graph from stored extractions (no writes)
    python -m riskweave_api.ingestion.pipeline_cli build --snapshot-id 3

Extraction commits after every chunk, so a run that is interrupted resumes from
where it stopped — re-running is safe and idempotent (per-chunk extraction runs
are keyed and skipped once completed).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from riskweave.graph.build_live import assemble_live_from_db, resolve_snapshot
from riskweave_api.extraction.gemini import (
    GeminiExtractionClient,
    GeminiResponseError,
    GeminiRestTransport,
)
from riskweave_api.extraction.service import ExtractionService, OffsetMismatchError
from riskweave_api.ingestion.database import session_factory
from riskweave_api.ingestion.models import (
    Document,
    DocumentChunk,
    ExtractionRun,
    RelationshipExtraction,
    SnapshotMember,
)

logger = logging.getLogger("riskweave_api.pipeline")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required for this command")
    return value


def _snapshot_chunk_ids(session: Session, snapshot_id: int) -> list[int]:
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


def _diagnose(session: Session, snapshot_id: int) -> int:
    snapshot = resolve_snapshot(session, snapshot_id=snapshot_id)
    chunk_ids = _snapshot_chunk_ids(session, snapshot.id)
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
    print(f"snapshot: id={snapshot.id} name={snapshot.name!r} frozen_at={snapshot.frozen_at}")
    print(f"chunks in snapshot: {len(chunk_ids)}")
    print(f"relationship_extractions total: {rel_total}")
    print(f"relationship_extractions for snapshot {snapshot.id}: {rel_for_snapshot}")
    print(f"extraction_runs by status: {dict(run_rows)}")
    return 0


def _extract(session: Session, snapshot_id: int, limit: int | None) -> int:
    api_key = SecretStr(_require_env("GEMINI_API_KEY"))
    client = GeminiExtractionClient(GeminiRestTransport(api_key), api_key=api_key)
    service = ExtractionService(session, client)

    snapshot = resolve_snapshot(session, snapshot_id=snapshot_id)
    chunk_ids = _snapshot_chunk_ids(session, snapshot.id)
    if limit is not None:
        chunk_ids = chunk_ids[:limit]
    total = len(chunk_ids)
    logger.info("extracting relationships snapshot=%s chunks=%s", snapshot.id, total)

    inserted = 0
    skipped = 0
    failed = 0
    started = time.monotonic()
    for index, chunk_id in enumerate(chunk_ids, start=1):
        try:
            result = service.extract_relationships_for_chunk(snapshot.id, chunk_id)
            inserted += result.inserted
            skipped += int(result.skipped_existing)
        except (GeminiResponseError, OffsetMismatchError) as exc:
            failed += 1
            logger.warning("chunk %s failed: %s", chunk_id, exc)
        # Commit after every chunk so the run is durable and resumable.
        session.commit()
        if index % 50 == 0 or index == total:
            elapsed = time.monotonic() - started
            logger.info(
                "progress %s/%s inserted=%s skipped=%s failed=%s elapsed=%.0fs",
                index,
                total,
                inserted,
                skipped,
                failed,
                elapsed,
            )
    print(
        f"extraction complete snapshot={snapshot.id} chunks={total} "
        f"inserted={inserted} skipped_existing={skipped} failed={failed}"
    )
    return 0


def _build(session: Session, snapshot_id: int, graph_version: str) -> int:
    result, snapshot = assemble_live_from_db(
        session, snapshot_id=snapshot_id, graph_version=graph_version
    )
    print(result.graph.stats_report())
    report = result.report
    print(
        f"relationships seen: {report.relationships_seen}, edges built: {report.edges_built}, "
        f"entity coverage: {report.entity_coverage}"
    )
    print(f"resolution layers: {report.resolution_layers}")
    print(f"drops by reason: {report.drops_by_reason}")
    print(f"default factors: {result.default_factors}")
    print(f"checksum: {result.graph.checksum}")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RiskWeave live pipeline runner (RIS-28).")
    sub = parser.add_subparsers(dest="command", required=True)

    diag = sub.add_parser("diagnose", help="print DB counts for a snapshot (no Gemini calls)")
    diag.add_argument("--snapshot-id", type=int, required=True)

    extract = sub.add_parser("extract", help="run Gemini relationship extraction over a snapshot")
    extract.add_argument("--snapshot-id", type=int, required=True)
    extract.add_argument("--limit", type=int, default=None, help="cap chunks processed this run")

    build = sub.add_parser("build", help="assemble + report the live graph from stored extractions")
    build.add_argument("--snapshot-id", type=int, required=True)
    build.add_argument("--graph-version", default="live-1.0.0")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    database_url = _require_env("DATABASE_URL")
    with session_factory(database_url)() as session:
        if args.command == "diagnose":
            return _diagnose(session, args.snapshot_id)
        if args.command == "extract":
            return _extract(session, args.snapshot_id, args.limit)
        if args.command == "build":
            return _build(session, args.snapshot_id, args.graph_version)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Run the live pipeline (extraction -> resolution -> derivation -> assembly).

RIS-28 operational entry point. Runs the RIS-10 Gemini extraction pass over a
frozen ingestion snapshot's chunks, then assembles the live graph (RIS-9/11/12)
from the stored relationships. Designed to run as a Railway one-off in the
``ingestion``/``backend`` image, where ``DATABASE_URL`` and ``GEMINI_API_KEY``
are present. The same operations are exposed over HTTP by the guarded
``/admin/pipeline`` endpoints (shared logic in :mod:`.pipeline`).

Subcommands (run from ``backend/``)::

    python -m riskweave_api.ingestion.pipeline_cli diagnose --snapshot-id 3
    python -m riskweave_api.ingestion.pipeline_cli extract --snapshot-id 3
    python -m riskweave_api.ingestion.pipeline_cli extract --snapshot-id 3 --limit 200
    python -m riskweave_api.ingestion.pipeline_cli build --snapshot-id 3

Extraction commits after every chunk, so an interrupted run resumes where it
stopped (already-completed per-chunk runs are skipped).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from pydantic import SecretStr
from sqlalchemy.orm import Session

from riskweave.graph.build_live import assemble_live_from_db
from riskweave_api.ingestion.database import session_factory
from riskweave_api.ingestion.pipeline import ExtractionProgress, diagnose, run_extraction

logger = logging.getLogger("riskweave_api.pipeline")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required for this command")
    return value


def _diagnose(session: Session, snapshot_id: int) -> int:
    report = diagnose(session, snapshot_id)
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0


def _log_progress(state: ExtractionProgress) -> None:
    if state.processed % 50 == 0 or state.processed == state.total:
        logger.info(
            "progress %s/%s inserted=%s skipped=%s failed=%s",
            state.processed,
            state.total,
            state.inserted,
            state.skipped,
            state.failed,
        )


def _extract(session: Session, snapshot_id: int, limit: int | None) -> int:
    api_key = SecretStr(_require_env("GEMINI_API_KEY"))
    state = run_extraction(
        session, snapshot_id, api_key=api_key, limit=limit, progress=_log_progress
    )
    print(
        f"extraction complete snapshot={state.snapshot_id} chunks={state.total} "
        f"inserted={state.inserted} skipped_existing={state.skipped} failed={state.failed}"
    )
    return 0


def _build(session: Session, snapshot_id: int, graph_version: str) -> int:
    result, _snapshot = assemble_live_from_db(
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

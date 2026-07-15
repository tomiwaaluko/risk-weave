"""Build the live knowledge graph from a real ingestion snapshot (RIS-28).

Runs resolution + derivation + assembly over the ``relationship_extractions``
already produced by the RIS-10 Gemini extraction pass for one immutable
ingestion snapshot (`RW-FR-015`), then writes a committed live-graph artifact
that the ``/graph/live`` endpoint serves — replacing the hand-authored demo
fixture as the product's real data source.

Usage (from ``backend/`` with ``.env`` loaded so ``DATABASE_URL`` is set)::

    # snapshot_id 3 is the frozen Railway snapshot proven in RIS-25
    uv run python -m riskweave.graph.build_live --snapshot-id 3
    uv run python -m riskweave.graph.build_live --snapshot-name demo-2026-07-12

The step is deterministic and reproducible: re-running against the same frozen
snapshot reproduces the same graph checksum. To bind the live graph to a *new*
ingestion snapshot, freeze the new snapshot and re-run with its id — nothing
else changes. See ``docs/live-pipeline.md``.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from riskweave.entity_resolution import Resolver
from riskweave_api.ingestion.database import session_factory
from riskweave_api.ingestion.models import DataSnapshot, Document, RelationshipExtraction

from .assembly import load_universe
from .live import ExtractedRelationship, LiveBuildResult, build_live_graph, graph_to_artifact

# backend/riskweave/graph/build_live.py -> parents[3] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_UNIVERSE = REPO_ROOT / "data" / "universe" / "entities.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "data" / "live" / "graph.json"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble the live graph from a snapshot (RIS-28)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot-id", type=int, help="DataSnapshot.id to assemble from.")
    group.add_argument("--snapshot-name", help="DataSnapshot.name to assemble from.")
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--corrections", type=Path, default=None)
    parser.add_argument("--graph-version", default="live-1.0.0")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Overrides the DATABASE_URL environment variable.",
    )
    return parser.parse_args(argv)


class SnapshotNotFoundError(LookupError):
    """Raised when the requested ingestion snapshot does not exist."""


def resolve_snapshot(
    session: Session, *, snapshot_id: int | None = None, snapshot_name: str | None = None
) -> DataSnapshot:
    """Look up a ``DataSnapshot`` by numeric id or name."""
    if snapshot_id is not None:
        snapshot = session.get(DataSnapshot, snapshot_id)
    elif snapshot_name is not None:
        snapshot = session.scalar(select(DataSnapshot).where(DataSnapshot.name == snapshot_name))
    else:
        raise ValueError("provide snapshot_id or snapshot_name")
    if snapshot is None:
        raise SnapshotNotFoundError(f"snapshot not found: {snapshot_id or snapshot_name}")
    return snapshot


def assemble_live_from_db(
    session: Session,
    *,
    snapshot_id: int | None = None,
    snapshot_name: str | None = None,
    universe_path: Path = DEFAULT_UNIVERSE,
    corrections_path: Path | None = None,
    graph_version: str = "live-1.0.0",
) -> tuple[LiveBuildResult, DataSnapshot]:
    """Resolve a snapshot and assemble its live graph from stored extractions.

    The single reusable entry point shared by the ``build_live`` CLI and the
    ``/graph/live`` endpoint, so both derive the graph identically from the
    database (`RW-FR-015`).
    """
    snapshot = resolve_snapshot(session, snapshot_id=snapshot_id, snapshot_name=snapshot_name)
    universe_entities = load_universe(str(universe_path))
    resolver = Resolver.from_universe_file(universe_path, corrections_path=corrections_path)
    relationships = load_relationships(session, snapshot.id)
    result = build_live_graph(
        relationships,
        resolver,
        universe_entities,
        snapshot_id=snapshot.name or f"snapshot-{snapshot.id}",
        graph_version=graph_version,
    )
    return result, snapshot


def _resolve_snapshot(session: Session, args: argparse.Namespace) -> DataSnapshot:
    try:
        return resolve_snapshot(
            session, snapshot_id=args.snapshot_id, snapshot_name=args.snapshot_name
        )
    except SnapshotNotFoundError as exc:
        raise SystemExit(str(exc)) from exc


def load_relationships(session: Session, snapshot_db_id: int) -> list[ExtractedRelationship]:
    """Load stored relationship extractions for a snapshot, joined to filing dates."""
    rows = session.execute(
        select(RelationshipExtraction, Document.filing_date)
        .join(
            Document,
            Document.source_document_id == RelationshipExtraction.source_document_id,
        )
        .where(RelationshipExtraction.snapshot_id == snapshot_db_id)
    ).all()
    relationships: list[ExtractedRelationship] = []
    for extraction, filing_date in rows:
        relationships.append(
            ExtractedRelationship(
                source_entity=extraction.source_entity,
                target_entity=extraction.target_entity,
                relationship_type=extraction.relationship_type,
                direction=extraction.direction,
                disclosed_magnitude=extraction.disclosed_magnitude,
                source_passage=extraction.source_passage,
                source_document_id=extraction.source_document_id,
                char_start=extraction.char_start,
                char_end=extraction.char_end,
                extraction_confidence=extraction.extraction_confidence,
                filing_date=filing_date,
                # Static disclosure: the data timestamp is the filing date.
                data_timestamp=datetime.combine(filing_date, time()),
            )
        )
    return relationships


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.database_url:
        raise SystemExit("DATABASE_URL is not set; load .env or pass --database-url.")

    universe_entities = load_universe(str(args.universe))
    resolver = Resolver.from_universe_file(args.universe, corrections_path=args.corrections)

    factory = session_factory(args.database_url)
    with factory() as session:
        snapshot = _resolve_snapshot(session, args)
        snapshot_string_id = snapshot.name or f"snapshot-{snapshot.id}"
        relationships = load_relationships(session, snapshot.id)

    result = build_live_graph(
        relationships,
        resolver,
        universe_entities,
        snapshot_id=snapshot_string_id,
        graph_version=args.graph_version,
    )

    print(result.graph.stats_report())
    report = result.report
    print(
        f"relationships seen: {report.relationships_seen}, edges built: {report.edges_built}, "
        f"entity coverage: {report.entity_coverage}"
    )
    print(f"resolution layers: {report.resolution_layers}")
    print(f"drops by reason: {report.drops_by_reason}")

    artifact = graph_to_artifact(
        result,
        note=(
            f"Live graph assembled from ingestion snapshot {snapshot_string_id} "
            f"(DataSnapshot.id={snapshot.id}) via RIS-28 build_live."
        ),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote live graph artifact to {args.out} (checksum {result.graph.checksum[:12]})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

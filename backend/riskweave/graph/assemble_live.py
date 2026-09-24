"""Assemble (and optionally Neo4j-seed) a live graph from extracted rows (RIS-28).

Does **not** run Gemini extraction. Operators must already have persisted
relationship rows for the target snapshot (e.g. snapshot_id=3 on Railway).

Usage (from ``backend/`` with ``DATABASE_URL`` set)::

    uv run python -m riskweave.graph.assemble_live --snapshot-id 3
    uv run python -m riskweave.graph.assemble_live --snapshot-id 3 --seed-neo4j

Environment:

* ``DATABASE_URL`` — required for loading extraction rows
* ``LIVE_GRAPH_SNAPSHOT_ID`` — default snapshot when ``--snapshot-id`` omitted
* ``NEO4J_*`` — only required with ``--seed-neo4j``
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from riskweave.entity_resolution import Resolver
from riskweave.graph.live import (
    DEFAULT_UNIVERSE_PATH,
    GRAPH_VERSION_DEFAULT,
    LiveAssemblyError,
    assemble_live_graph,
)
from riskweave.graph.store import Neo4jGraphStore, Neo4jUnavailableError, coverage_report


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    default_snap = os.environ.get("LIVE_GRAPH_SNAPSHOT_ID", "3")
    parser = argparse.ArgumentParser(
        description=(
            "Assemble a provenanced graph from already-extracted snapshot rows "
            "(RIS-28). Does not call Gemini."
        )
    )
    parser.add_argument(
        "--snapshot-id",
        type=int,
        default=int(default_snap),
        help="Postgres data_snapshots.id (default: LIVE_GRAPH_SNAPSHOT_ID or 3).",
    )
    parser.add_argument(
        "--universe",
        type=Path,
        default=DEFAULT_UNIVERSE_PATH,
        help="Path to data/universe/entities.json",
    )
    parser.add_argument(
        "--corrections",
        type=Path,
        default=None,
        help="Optional JSONL corrections file for entity resolution.",
    )
    parser.add_argument(
        "--graph-version",
        default=GRAPH_VERSION_DEFAULT,
        help="Graph version string stamped on the assembled graph.",
    )
    parser.add_argument(
        "--seed-neo4j",
        action="store_true",
        help="Drop-reload the assembled graph into Neo4j after assembly.",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("NEO4J_DATABASE"),
        help="Neo4j database name (default: server default).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("error: DATABASE_URL is required", file=sys.stderr)
        return 1

    # Local imports keep the module importable when SQLAlchemy/API deps are
    # present (always in this package) without circular imports at collect time.
    from riskweave_api.graph.live_loader import load_extracted_relationships
    from riskweave_api.ingestion.database import session_factory

    factory = session_factory(database_url)
    try:
        with factory() as session:
            relationships = load_extracted_relationships(session, args.snapshot_id)
    except LiveAssemblyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - connection failures
        print(f"error: failed to load extractions: {exc}", file=sys.stderr)
        return 1

    resolver = Resolver.from_universe_file(args.universe, corrections_path=args.corrections)
    snapshot_label = f"live-snapshot-{args.snapshot_id}"
    try:
        graph, report = assemble_live_graph(
            snapshot_id=snapshot_label,
            relationships=relationships,
            resolver=resolver,
            universe_path=args.universe,
            graph_version=args.graph_version,
        )
    except LiveAssemblyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(graph.stats_report())
    print(
        f"assembly report: seen={report.relationships_seen} "
        f"edges={report.edges_built} unresolved={report.skipped_unresolved} "
        f"no_weight={report.skipped_no_weight} unknown_type={report.skipped_unknown_type} "
        f"duplicate={report.skipped_duplicate} "
        f"methods={dict(report.method_counts)}"
    )

    if not args.seed_neo4j:
        print(
            "assembled in-memory only; pass --seed-neo4j to write Neo4j, "
            "or POST /graph/seed?source=live to register the scenario."
        )
        return 0

    try:
        uri = os.environ["NEO4J_URI"]
        user = os.environ["NEO4J_USER"]
        password = os.environ["NEO4J_PASSWORD"]
    except KeyError as exc:
        print(
            f"error: missing {exc.args[0]}; required with --seed-neo4j",
            file=sys.stderr,
        )
        return 1

    try:
        store = Neo4jGraphStore.connect(uri, user, password, database=args.database)
    except Neo4jUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        counts = store.seed(graph)
        print(f"seeded {counts['nodes']} nodes and {counts['edges']} edges into Neo4j at {uri}")
        cov = coverage_report(graph)
        print(
            f"provenance coverage: {cov['coverage']:.0%} "
            f"({cov['provenanced_edges']}/{cov['total_edges']} edges)"
        )
    except Exception as exc:
        print(f"error: failed to seed Neo4j: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

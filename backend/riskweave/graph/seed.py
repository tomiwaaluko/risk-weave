"""Seed the local Neo4j instance from the committed graph fixture (RIS-12).

Usage (from ``backend/`` with the Compose stack up and ``.env`` loaded)::

    uv run python -m riskweave.graph.seed
    uv run python -m riskweave.graph.seed --fixture data/fixtures/cre_graph.json

Reads the Neo4j connection from the environment (``NEO4J_URI``, ``NEO4J_USER``,
``NEO4J_PASSWORD``), loads and validates the fixture through the Graft 2 write
gate, then drop-reloads it into Neo4j. Re-running reproduces the same graph.

Requires the ``neo4j`` driver (``uv add neo4j``); the seed exits with a clear
message if it is not installed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .fixture import DEFAULT_FIXTURE_PATH, load_graph_fixture
from .store import Neo4jGraphStore, Neo4jUnavailableError


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Neo4j from the graph fixture (RIS-12).")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Path to the fixture JSON (default: bundled CRE fixture).",
    )
    parser.add_argument(
        "--pack",
        default=None,
        help="Optional pack to report the engine-ready snapshot for (e.g. 'cre').",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("NEO4J_DATABASE"),
        help="Neo4j database name (default: server default).",
    )
    return parser.parse_args(argv)


def _connection_from_env() -> tuple[str, str, str]:
    try:
        uri = os.environ["NEO4J_URI"]
        user = os.environ["NEO4J_USER"]
        password = os.environ["NEO4J_PASSWORD"]
    except KeyError as exc:
        raise SystemExit(
            f"missing required environment variable {exc.args[0]}; "
            "set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD (see .env.example)."
        ) from exc
    return uri, user, password


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    graph = load_graph_fixture(args.fixture)
    print(graph.stats_report())

    uri, user, password = _connection_from_env()
    try:
        store = Neo4jGraphStore.connect(uri, user, password, database=args.database)
    except Neo4jUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        counts = store.seed(graph)
        print(f"seeded {counts['nodes']} nodes and {counts['edges']} edges into Neo4j at {uri}")
        snapshot = store.read_snapshot(pack=args.pack)
        print(
            f"read-back snapshot {snapshot.snapshot_id} v{snapshot.graph_version}: "
            f"{len(snapshot.nodes)} nodes, {len(snapshot.edges)} edges"
            + (f" (pack={args.pack})" if args.pack else "")
        )
    finally:
        store.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

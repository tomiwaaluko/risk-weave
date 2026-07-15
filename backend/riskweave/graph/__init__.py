"""Knowledge-graph assembly with the Graft 2 write gate (RIS-12).

Fixture loading and the Neo4j store are exposed here too, but the store's
``neo4j`` driver is imported lazily inside :mod:`riskweave.graph.store` so this
package imports cleanly without the driver installed.
"""

from .assembly import (
    AssembledGraph,
    GraphAssemblyError,
    ProposedEdge,
    UniverseEntity,
    assemble,
    load_universe,
)
from .centrality import transmission_centrality
from .fixture import DEFAULT_FIXTURE_PATH, FixtureError, load_graph_fixture
from .live import (
    ExtractedRelationship,
    LiveBuildReport,
    LiveBuildResult,
    build_live_graph,
    graph_to_artifact,
)
from .store import (
    Neo4jGraphStore,
    Neo4jUnavailableError,
    Neo4jWriteError,
    coverage_report,
    validate_edge_row,
)

__all__ = [
    "AssembledGraph",
    "GraphAssemblyError",
    "ProposedEdge",
    "UniverseEntity",
    "assemble",
    "load_universe",
    "transmission_centrality",
    "DEFAULT_FIXTURE_PATH",
    "FixtureError",
    "load_graph_fixture",
    "ExtractedRelationship",
    "LiveBuildReport",
    "LiveBuildResult",
    "build_live_graph",
    "graph_to_artifact",
    "Neo4jGraphStore",
    "Neo4jUnavailableError",
    "Neo4jWriteError",
    "coverage_report",
    "validate_edge_row",
]

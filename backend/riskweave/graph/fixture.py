"""Load the committed knowledge-graph fixture (RIS-12, reduced hackathon scope).

Under the reduced scope the graph is not extracted live: a small curated
fixture (``data/fixtures/cre_graph.json``) carries ~15 CRE-pack entities and
typed, weighted, directed edges whose weights and provenance are **pre-baked**
(hand-authored from real filing disclosures where practical), rather than
produced by the deferred Gemini extraction pipeline (RIS-10/11).

The loader still routes every pre-baked edge through the same Graft 2 write
gate as the live path: each edge weight is materialized as a
:class:`~riskweave.derivations.WeightRecord` bound to a validated
:class:`~riskweave.derivations.Provenance`, then handed to
:func:`~riskweave.graph.assemble`. A fixture edge missing any provenance field
is therefore rejected at load, not silently loaded (`RW-ALG-032`) — the fixture
is pre-baked, but not un-provenanced.

The returned :class:`~riskweave.graph.AssembledGraph` is the single source the
Neo4j seed writes from and the propagation engine ultimately reads.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path

from riskweave.derivations import Provenance, WeightRecord

from .assembly import AssembledGraph, GraphAssemblyError, ProposedEdge, UniverseEntity, assemble

# ``fixture.py`` lives at ``backend/riskweave/graph/`` → parents[2] is ``backend``.
DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "cre_graph.json"


class FixtureError(GraphAssemblyError):
    """Raised when the fixture file is structurally malformed.

    Subclasses :class:`GraphAssemblyError` so any fixture problem — a bad shape
    here or a Graft 2 violation downstream — surfaces as a single failure type.
    """


def _require(record: Mapping, key: str, where: str):
    if key not in record:
        raise FixtureError(f"{where} is missing required field {key!r}")
    return record[key]


def _build_provenance(prov: Mapping, where: str) -> Provenance:
    """Build a validated Provenance from a fixture edge's provenance block.

    ``char_end`` is derived as ``char_start + len(source_passage)`` so the
    committed offsets always match the passage exactly; the fixture author only
    supplies ``char_start``.
    """
    passage = _require(prov, "source_passage", where)
    if not isinstance(passage, str):
        raise FixtureError(f"{where}.source_passage must be a string")
    char_start = _require(prov, "char_start", where)
    if not isinstance(char_start, int) or isinstance(char_start, bool):
        raise FixtureError(f"{where}.char_start must be an integer")
    return Provenance(
        source_document_id=_require(prov, "source_document_id", where),
        filing_date=date.fromisoformat(_require(prov, "filing_date", where)),
        source_passage=passage,
        char_start=char_start,
        char_end=char_start + len(passage),
        data_timestamp=datetime.fromisoformat(_require(prov, "data_timestamp", where)),
        extraction_confidence=_require(prov, "extraction_confidence", where),
    )


def _build_edge(record: Mapping, index: int) -> ProposedEdge:
    where = f"edges[{index}]"
    weight = _require(record, "weight", where)
    prov_block = _require(weight, "provenance", f"{where}.weight")
    provenance = _build_provenance(prov_block, f"{where}.weight.provenance")
    timestamps = tuple(
        datetime.fromisoformat(ts) for ts in _require(weight, "data_timestamps", f"{where}.weight")
    )
    weight_record = WeightRecord(
        value=_require(weight, "value", f"{where}.weight"),
        method_id=_require(weight, "method_id", f"{where}.weight"),
        method_version=_require(weight, "method_version", f"{where}.weight"),
        inputs=dict(weight.get("inputs", {})),
        provenance=provenance,
        data_timestamps=timestamps,
    )
    return ProposedEdge(
        source_id=_require(record, "source_id", where),
        target_id=_require(record, "target_id", where),
        relationship_type=_require(record, "relationship_type", where),
        direction=_require(record, "direction", where),
        record=weight_record,
    )


def load_graph_fixture(path: str | Path = DEFAULT_FIXTURE_PATH) -> AssembledGraph:
    """Load, validate, and assemble the committed fixture into a graph.

    Raises :class:`FixtureError` on a malformed file and
    :class:`GraphAssemblyError` on any Graft 2 / universe violation.
    """
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)

    snapshot_id = _require(payload, "snapshot_id", "fixture")
    graph_version = _require(payload, "graph_version", "fixture")
    entities = tuple(
        UniverseEntity.from_universe_record(record)
        for record in _require(payload, "nodes", "fixture")
    )
    edge_records = _require(payload, "edges", "fixture")
    edges = tuple(_build_edge(record, i) for i, record in enumerate(edge_records))
    return assemble(snapshot_id, graph_version, entities, edges)

"""Fixture-backed demo graph endpoint with full provenance (RIS-20).

The RIS-15 spike (``/spike/seed``) exposes a 200-node *synthetic* graph whose
edges carry only opaque ``provenance_ref`` strings — enough to render a canvas,
but nothing to drill into. RIS-20 (evidence panels: the 30-second trace) needs
the opposite: every Graft 2 provenance field (`RW-ALG-032`) for every edge, so
a user can click a number and read the exact filing sentence behind it.

This router serves the committed CRE fixture graph (RIS-12) — ~15 real
entities whose edges carry complete, hand-authored provenance (quoted passage,
character offsets, filing date, as-of timestamp, extraction confidence) plus a
registered derivation method (`RW-ALG-004`). It registers the graph as a
runnable scenario so the existing propagation engine and WebSocket slider work
unchanged, and it echoes the human-readable derivation methodology
(`/graph/methodology`) for the honesty page.

RIS-28 adds an explicit **live** seed path (`?source=live`) that assembles a
graph from already-extracted snapshot rows + layered entity resolution +
registered ``DER-*`` derivations. The fixture remains the default so demo
freeze and existing tests stay intact. Live assembly never calls Gemini and
never silently substitutes the fixture unless ``fallback_to_fixture=true``.

Shock magnitudes here are set by deterministic code, never by Gemini
(`RW-AI-010`); they seed the primary CRE-decline demo cascade.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from riskweave.derivations.registry import list_methods
from riskweave.entity_resolution import Resolver
from riskweave.explain import EdgeEvidence
from riskweave.graph.assembly import AssembledGraph, GraphAssemblyError
from riskweave.graph.fixture import load_graph_fixture
from riskweave.graph.live import (
    DEFAULT_UNIVERSE_PATH,
    LiveAssemblyError,
    assemble_live_graph,
)
from riskweave_api.dependencies import get_store
from riskweave_api.models import ScenarioCreateRequest, ScenarioState, ShockFactorIn
from riskweave_api.scenario_store import ScenarioStore
from riskweave_api.security import default_rate_limit, require_api_key
from riskweave_api.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])
StoreDependency = Annotated[ScenarioStore, Depends(get_store)]

GRAPH_SCENARIO_ID = "cre-demo"
LIVE_GRAPH_SCENARIO_ID = "cre-live"
SEED = 20260711

# Deterministic CRE-decline demo shock (magnitudes chosen by code, not Gemini).
# Shocking the office sector cascades to REITs and their bank creditors; the
# metro origins add a second, geographic transmission path for a richer graph.
_DEMO_FACTORS: tuple[tuple[str, str, float], ...] = (
    ("cre-office-shock", "cre-office", 1.0),
    ("cre-multifamily-shock", "cre-multifamily", 0.6),
    ("nyc-metro-shock", "nyc-metro", 0.8),
)

# Below this extraction/data-quality confidence an edge is surfaced but badged
# low-confidence in the UI (`RW-SAFE-003` — labeled, never hidden). Kept in the
# payload so the client and any automated check share one threshold.
LOW_CONFIDENCE_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProvenanceOut(BaseModel):
    """Complete Graft 2 provenance for one edge weight (`RW-ALG-032`)."""

    source_document_id: str
    filing_date: str
    source_passage: str
    char_start: int
    char_end: int
    data_timestamp: str
    extraction_confidence: float


class GraphNodeOut(BaseModel):
    node_id: str
    node_type: str
    name: str
    # Structural transmission centrality — labeled separately from scenario
    # impact in the UI so the two channels never blur (`RW-FR-019`).
    centrality: float


class GraphEdgeOut(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relationship_type: str
    direction: str
    weight: float  # signed engine weight
    magnitude: float  # unsigned derivation output
    method_id: str
    method_version: str
    method_name: str  # human-readable §12.1 row label
    method_summary: str
    method_source_data: str
    provenance_ref: str
    provenance: ProvenanceOut


class GraphFactorOut(BaseModel):
    factor_id: str
    node_id: str
    magnitude: float


class GraphSeedResponse(BaseModel):
    scenario_id: str
    snapshot_id: str
    graph_version: str
    state: str
    checksum: str
    low_confidence_threshold: float
    source: Literal["fixture", "live"] = "fixture"
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    factors: list[GraphFactorOut]


class MethodOut(BaseModel):
    method_id: str
    version: str
    name: str
    source_data: str
    summary: str
    variants: list[str]


class MethodologyResponse(BaseModel):
    low_confidence_threshold: float
    methods: list[MethodOut]
    data_sources: list[str]
    limitations: list[str]


class LiveAssemblyInfo(BaseModel):
    """Operator-facing binding for the live pipeline (RIS-28)."""

    default_snapshot_id: int
    graph_version: str
    assemble_command: str
    notes: list[str]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _provenance_by_edge(graph: AssembledGraph) -> dict[str, EdgeEvidence]:
    """Map each fixture edge to its pre-baked provenance for RIS-19 citations.

    ``citation_id`` and node display names are placeholders here; explanation
    generation reassigns stable ``cit-N`` ids and resolves names per run.
    """
    records: dict[str, EdgeEvidence] = {}
    for edge in graph.edges:
        prov = edge.record.provenance
        records[edge.edge_id] = EdgeEvidence(
            citation_id="",
            edge_id=edge.edge_id,
            source_name=edge.source_id,
            target_name=edge.target_id,
            relationship_type=edge.relationship_type,
            method_id=edge.record.method_id,
            source_document_id=prov.source_document_id,
            source_passage=prov.source_passage,
            char_start=prov.char_start,
            char_end=prov.char_end,
            filing_date=prov.filing_date.isoformat(),
            data_timestamp=prov.data_timestamp.isoformat(),
            extraction_confidence=prov.extraction_confidence,
        )
    return records


def _serialize_graph(
    graph: AssembledGraph,
    *,
    scenario_id: str,
    source: Literal["fixture", "live"],
    factors: tuple[tuple[str, str, float], ...],
) -> GraphSeedResponse:
    from riskweave.derivations.registry import get_method

    nodes = [
        GraphNodeOut(
            node_id=e.entity_id,
            node_type=e.entity_type,
            name=e.canonical_name,
            centrality=graph.centrality[e.entity_id],
        )
        for e in graph.entities
    ]

    edges: list[GraphEdgeOut] = []
    for edge in graph.edges:
        method = get_method(edge.record.method_id)
        prov = edge.record.provenance
        edges.append(
            GraphEdgeOut(
                edge_id=edge.edge_id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                relationship_type=edge.relationship_type,
                direction=edge.direction,
                weight=edge.signed_weight,
                magnitude=edge.record.value,
                method_id=edge.record.method_id,
                method_version=edge.record.method_version,
                method_name=method.spec_row,
                method_summary=method.summary,
                method_source_data=method.source_data,
                provenance_ref=edge.provenance_ref,
                provenance=ProvenanceOut(
                    source_document_id=prov.source_document_id,
                    filing_date=prov.filing_date.isoformat(),
                    source_passage=prov.source_passage,
                    char_start=prov.char_start,
                    char_end=prov.char_end,
                    data_timestamp=prov.data_timestamp.isoformat(),
                    extraction_confidence=prov.extraction_confidence,
                ),
            )
        )

    factor_out = [
        GraphFactorOut(factor_id=fid, node_id=nid, magnitude=mag) for fid, nid, mag in factors
    ]

    return GraphSeedResponse(
        scenario_id=scenario_id,
        snapshot_id=graph.snapshot_id,
        graph_version=graph.graph_version,
        state=ScenarioState.READY,
        checksum=graph.checksum,
        low_confidence_threshold=LOW_CONFIDENCE_THRESHOLD,
        source=source,
        nodes=nodes,
        edges=edges,
        factors=factor_out,
    )


def _register_scenario(
    store: ScenarioStore,
    graph: AssembledGraph,
    *,
    scenario_id: str,
    factors: tuple[tuple[str, str, float], ...],
) -> None:
    snapshot = graph.to_snapshot()
    store.register_snapshot(snapshot)
    store.register_provenance(snapshot.snapshot_id, _provenance_by_edge(graph))
    store.delete_scenario(scenario_id)
    req = ScenarioCreateRequest(
        scenario_id=scenario_id,
        snapshot_id=snapshot.snapshot_id,
        graph_version=snapshot.graph_version,
        factors=[
            ShockFactorIn(factor_id=fid, node_id=nid, magnitude=mag) for fid, nid, mag in factors
        ],
        seed=SEED,
    )
    store.create(req)
    store.transition(scenario_id, ScenarioState.VALIDATING)
    store.transition(scenario_id, ScenarioState.READY)


def _live_factors_for(graph: AssembledGraph) -> tuple[tuple[str, str, float], ...]:
    """Pick shock factors whose nodes exist in the live graph.

    Prefer the curated demo factor nodes; if none resolve (full universe ids
    differ from the fixture), fall back to the highest-centrality node so the
    scenario is still runnable.
    """
    known = {e.entity_id for e in graph.entities}
    matched = tuple(f for f in _DEMO_FACTORS if f[1] in known)
    if matched:
        return matched
    if not graph.entities:
        return ()
    top = max(graph.entities, key=lambda e: graph.centrality.get(e.entity_id, 0.0))
    return (("live-origin-shock", top.entity_id, 1.0),)


def _assemble_live(
    settings: Settings,
    snapshot_id: int,
    factory: sessionmaker[Session],
) -> AssembledGraph:
    from riskweave_api.graph.live_loader import load_extracted_relationships

    try:
        with factory() as session:
            relationships = load_extracted_relationships(session, snapshot_id)
    except LiveAssemblyError:
        raise
    except Exception as exc:
        logger.exception("failed to load extractions for snapshot_id=%s", snapshot_id)
        raise LiveAssemblyError(
            f"failed to load extractions for snapshot_id={snapshot_id}"
        ) from exc

    universe = DEFAULT_UNIVERSE_PATH
    if not Path(universe).exists():
        raise LiveAssemblyError(f"universe file not found: {universe}")
    resolver = Resolver.from_universe_file(universe)
    graph, _report = assemble_live_graph(
        snapshot_id=f"live-snapshot-{snapshot_id}",
        relationships=relationships,
        resolver=resolver,
        universe_path=universe,
        graph_version=settings.live_graph_version,
    )
    return graph


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/seed",
    response_model=GraphSeedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key), Depends(default_rate_limit)],
)
def seed_graph(
    request: Request,
    store: StoreDependency,
    source: Literal["fixture", "live"] = Query(
        default="fixture",
        description=(
            "Graph source. 'fixture' (default) loads the committed CRE demo "
            "fixture. 'live' assembles from already-extracted rows for the "
            "configured snapshot (LIVE_GRAPH_SNAPSHOT_ID)."
        ),
    ),
    snapshot_id: int | None = Query(
        default=None,
        description="Override LIVE_GRAPH_SNAPSHOT_ID when source=live.",
    ),
    fallback_to_fixture: bool = Query(
        default=False,
        description=(
            "When source=live and assembly fails, return the fixture instead "
            "of an error. Off by default so missing extractions are visible."
        ),
    ),
) -> GraphSeedResponse:
    """Seed a runnable graph scenario.

    Default ``source=fixture`` preserves the demo freeze and existing tests.
    ``source=live`` requires already-persisted extraction rows and never calls
    Gemini (`RW-AI-010`).
    """
    settings: Settings = request.app.state.settings
    graph_source: Literal["fixture", "live"] = source
    scenario_id = GRAPH_SCENARIO_ID
    factors = _DEMO_FACTORS

    if source == "live":
        live_snap = snapshot_id if snapshot_id is not None else settings.live_graph_snapshot_id
        try:
            graph = _assemble_live(
                settings,
                live_snap,
                request.app.state.db_session_factory,
            )
            scenario_id = LIVE_GRAPH_SCENARIO_ID
            factors = _live_factors_for(graph)
        except LiveAssemblyError as exc:
            if not fallback_to_fixture:
                raise HTTPException(
                    status_code=422,
                    detail=str(exc),
                ) from exc
            try:
                graph = load_graph_fixture()
            except GraphAssemblyError as fixture_exc:  # pragma: no cover
                raise HTTPException(
                    status_code=500, detail=f"fixture load failed: {fixture_exc}"
                ) from fixture_exc
            graph_source = "fixture"
            scenario_id = GRAPH_SCENARIO_ID
            factors = _DEMO_FACTORS
    else:
        try:
            graph = load_graph_fixture()
        except GraphAssemblyError as exc:  # pragma: no cover - fixture is committed
            raise HTTPException(status_code=500, detail=f"fixture load failed: {exc}") from exc

    _register_scenario(store, graph, scenario_id=scenario_id, factors=factors)
    return _serialize_graph(graph, scenario_id=scenario_id, source=graph_source, factors=factors)


@router.get(
    "/live-info",
    response_model=LiveAssemblyInfo,
    dependencies=[Depends(default_rate_limit)],
)
def get_live_assembly_info(request: Request) -> LiveAssemblyInfo:
    """Document snapshot binding and the operator assemble command (RIS-28)."""
    settings: Settings = request.app.state.settings
    snap = settings.live_graph_snapshot_id
    return LiveAssemblyInfo(
        default_snapshot_id=snap,
        graph_version=settings.live_graph_version,
        assemble_command=(f"uv run python -m riskweave.graph.assemble_live --snapshot-id {snap}"),
        notes=[
            f"Live seed binds to immutable snapshot_id={snap} (RW-FR-015). "
            "Override with LIVE_GRAPH_SNAPSHOT_ID or ?snapshot_id=.",
            "POST /graph/seed?source=live assembles from already-extracted "
            "relationship rows; it does not call Gemini (RW-AI-010).",
            "Full Gemini extraction over snapshot 3's ~22k chunks is an "
            "operator step (cost/budget), not part of the seed request.",
            "Fixture remains the default: POST /graph/seed or ?source=fixture.",
            "Optional Neo4j write: add --seed-neo4j to the assemble_live command.",
        ],
    )


@router.get(
    "/methodology",
    response_model=MethodologyResponse,
    dependencies=[Depends(default_rate_limit)],
)
def get_methodology() -> MethodologyResponse:
    """Human-readable derivation methods + data-source honesty notes.

    Backs the methodology/honesty page (`RW-DATA-002`): every §12.1 method with
    its source data, plus the known limitations a viewer must see to trust the
    numbers.
    """
    methods = [
        MethodOut(
            method_id=m.method_id,
            version=m.version,
            name=m.spec_row,
            source_data=m.source_data,
            summary=m.summary,
            variants=list(m.variants),
        )
        for m in list_methods()
    ]
    return MethodologyResponse(
        low_confidence_threshold=LOW_CONFIDENCE_THRESHOLD,
        methods=methods,
        data_sources=[
            "SEC EDGAR filings (10-K / 10-Q disclosures) — free tier, rate-limited",
            "XBRL company facts (segment and concentration figures)",
            "FRED economic and commodity time series — free tier",
        ],
        limitations=[
            "Equity-price sensitivities use limited free-tier history; betas are "
            "indicative, not risk-model grade (RW-DATA-002).",
            "The default demo graph is a reduced, curated CRE fixture (~15 entities); "
            "POST /graph/seed?source=live assembles from extracted snapshot rows "
            "when available (RIS-28).",
            "Edge weights are always produced by registered DER-* methods; Gemini "
            "only captures passages and disclosed_magnitude strings (RW-AI-010).",
            "Analytics only — no price predictions and no buy/sell/hold advice.",
        ],
    )

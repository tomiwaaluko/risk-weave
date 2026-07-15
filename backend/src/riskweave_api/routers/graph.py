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

Shock magnitudes here are set by deterministic code, never by Gemini
(`RW-AI-010`); they seed the primary CRE-decline demo cascade.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from riskweave.derivations.registry import list_methods
from riskweave.explain import EdgeEvidence
from riskweave.graph.assembly import AssembledGraph, GraphAssemblyError
from riskweave.graph.fixture import load_graph_fixture
from riskweave_api.dependencies import get_store
from riskweave_api.models import ScenarioCreateRequest, ScenarioState, ShockFactorIn
from riskweave_api.scenario_store import ScenarioStore
from riskweave_api.security import default_rate_limit, require_api_key

router = APIRouter(prefix="/graph", tags=["graph"])
StoreDependency = Annotated[ScenarioStore, Depends(get_store)]

GRAPH_SCENARIO_ID = "cre-demo"
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


def _serialize_graph(graph: AssembledGraph) -> GraphSeedResponse:
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

    factors = [
        GraphFactorOut(factor_id=fid, node_id=nid, magnitude=mag) for fid, nid, mag in _DEMO_FACTORS
    ]

    return GraphSeedResponse(
        scenario_id=GRAPH_SCENARIO_ID,
        snapshot_id=graph.snapshot_id,
        graph_version=graph.graph_version,
        state=ScenarioState.READY,
        checksum=graph.checksum,
        low_confidence_threshold=LOW_CONFIDENCE_THRESHOLD,
        nodes=nodes,
        edges=edges,
        factors=factors,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/seed",
    response_model=GraphSeedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key), Depends(default_rate_limit)],
)
def seed_graph(store: StoreDependency) -> GraphSeedResponse:
    """Load the CRE fixture graph and register it as a runnable demo scenario.

    Idempotent: re-seeding overwrites the previous demo scenario. Every returned
    edge carries complete provenance — the write gate in the fixture loader
    rejects anything less before it reaches here (`RW-ALG-032`).
    """
    try:
        graph = load_graph_fixture()
    except GraphAssemblyError as exc:  # pragma: no cover - fixture is committed
        raise HTTPException(status_code=500, detail=f"fixture load failed: {exc}") from exc

    snapshot = graph.to_snapshot()
    store.register_snapshot(snapshot)
    store.register_provenance(snapshot.snapshot_id, _provenance_by_edge(graph))

    # Overwrite any previous demo scenario so re-seeding is idempotent.
    store.delete_scenario(GRAPH_SCENARIO_ID)

    req = ScenarioCreateRequest(
        scenario_id=GRAPH_SCENARIO_ID,
        snapshot_id=snapshot.snapshot_id,
        graph_version=snapshot.graph_version,
        factors=[
            ShockFactorIn(factor_id=fid, node_id=nid, magnitude=mag)
            for fid, nid, mag in _DEMO_FACTORS
        ],
        seed=SEED,
    )
    store.create(req)
    store.transition(GRAPH_SCENARIO_ID, ScenarioState.VALIDATING)
    store.transition(GRAPH_SCENARIO_ID, ScenarioState.READY)

    return _serialize_graph(graph)


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
            "The demo graph is a reduced, curated CRE fixture (~15 entities); it "
            "is not the full 100-200 entity universe.",
            "Edge weights are pre-baked deterministic-method outputs from real "
            "disclosures; the live Gemini extraction pipeline is deferred.",
            "Analytics only — no price predictions and no buy/sell/hold advice.",
        ],
    )

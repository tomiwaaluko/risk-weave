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

import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
GRAPH_LIVE_SCENARIO_ID = "cre-live"
SEED = 20260711

# ``backend/src/riskweave_api/routers/graph.py`` -> parents[3] is ``backend``.
# The live-graph artifact is produced by ``python -m riskweave.graph.build_live``
# from a real ingestion snapshot; the path is overridable for tests/deploys.
DEFAULT_LIVE_GRAPH_PATH = Path(__file__).resolve().parents[3] / "data" / "live" / "graph.json"


def _live_graph_path() -> Path:
    return Path(os.environ.get("RISKWEAVE_LIVE_GRAPH_PATH", str(DEFAULT_LIVE_GRAPH_PATH)))


def _live_snapshot_selector() -> tuple[int | None, str | None]:
    """Which ingestion snapshot the live endpoint binds to (`RW-FR-015`).

    Set ``RISKWEAVE_LIVE_SNAPSHOT_ID`` (e.g. ``3``, the frozen Railway snapshot)
    or ``RISKWEAVE_LIVE_SNAPSHOT_NAME`` to serve the graph built on demand from
    Postgres. Unset leaves the endpoint on the artifact-file path.
    """
    raw_id = os.environ.get("RISKWEAVE_LIVE_SNAPSHOT_ID")
    name = os.environ.get("RISKWEAVE_LIVE_SNAPSHOT_NAME")
    snapshot_id = int(raw_id) if raw_id and raw_id.strip() else None
    return snapshot_id, name


def _build_live_from_db(
    request: Request,
) -> tuple[AssembledGraph, tuple[tuple[str, str, float], ...]] | None:
    """Assemble the live graph on demand from the bound snapshot's extractions.

    Returns ``None`` when no snapshot is configured (endpoint stays on the
    artifact path). Raises 503 when a snapshot is configured but the database is
    unreachable or has no extractions yet — the durable serving path for
    Railway's ephemeral one-off extraction jobs.
    """
    snapshot_id, snapshot_name = _live_snapshot_selector()
    if snapshot_id is None and snapshot_name is None:
        return None

    from riskweave.graph.build_live import SnapshotNotFoundError, assemble_live_from_db
    from riskweave_api.ingestion.database import session_factory

    settings = request.app.state.settings
    graph_version = os.environ.get("RISKWEAVE_LIVE_GRAPH_VERSION", "live-1.0.0")
    try:
        factory = session_factory(settings.database_url)
        with factory() as session:
            result, _snapshot = assemble_live_from_db(
                session,
                snapshot_id=snapshot_id,
                snapshot_name=snapshot_name,
                graph_version=graph_version,
            )
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # database unreachable / driver error
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"live graph database is unavailable: {exc}",
        ) from exc

    if not result.graph.edges:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "no relationships extracted for the bound snapshot yet; run the "
                "extraction pass (python -m riskweave_api.ingestion.pipeline_cli "
                "extract) before serving the live graph."
            ),
        )
    return result.graph, result.default_factors


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


def _serialize_graph(
    graph: AssembledGraph,
    scenario_id: str,
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
        nodes=nodes,
        edges=edges,
        factors=factor_out,
    )


def _register_runnable_scenario(
    store: ScenarioStore,
    graph: AssembledGraph,
    scenario_id: str,
    factors: tuple[tuple[str, str, float], ...],
) -> None:
    """Register an assembled graph as a runnable scenario (idempotent).

    Shared by the fixture (``/graph/seed``) and live (``/graph/live``) paths so
    both drive the same propagation engine + WebSocket slider unchanged.
    """
    snapshot = graph.to_snapshot()
    store.register_snapshot(snapshot)
    store.register_provenance(snapshot.snapshot_id, _provenance_by_edge(graph))

    # Overwrite any previous scenario of this id so re-seeding is idempotent.
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

    _register_runnable_scenario(store, graph, GRAPH_SCENARIO_ID, _DEMO_FACTORS)
    return _serialize_graph(graph, GRAPH_SCENARIO_ID, _DEMO_FACTORS)


@router.post(
    "/live",
    response_model=GraphSeedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key), Depends(default_rate_limit)],
)
def seed_live_graph(store: StoreDependency, request: Request) -> GraphSeedResponse:
    """Serve the *live* graph assembled from real extraction output (RIS-28).

    Two sources, in priority order:

    1. **Database (real, durable).** When ``RISKWEAVE_LIVE_SNAPSHOT_ID`` /
       ``_NAME`` is set, assemble on demand from the bound ingestion snapshot's
       ``relationship_extractions`` — the output of running extraction (RIS-10) +
       resolution (RIS-11) + derivation (RIS-9) + assembly (RIS-12) end-to-end.
       This is the path Railway serves, since a one-off extraction job's
       filesystem is ephemeral.
    2. **Artifact file (offline/demo-freeze).** Otherwise load the artifact
       produced by ``python -m riskweave.graph.build_live``.

    Either way the graph is assembled through the Graft 2 write gate, so every
    *generated* edge carries full provenance (`RW-ALG-032`), and it is registered
    as a runnable scenario so the slider round-trips unchanged. Returns 503 when
    neither source is available; the curated CRE fixture remains at
    ``POST /graph/seed`` as the explicit fallback (`RW-NFR-005` spirit).
    """
    from_db = _build_live_from_db(request)
    if from_db is not None:
        graph, factors = from_db
        _register_runnable_scenario(store, graph, GRAPH_LIVE_SCENARIO_ID, factors)
        return _serialize_graph(graph, GRAPH_LIVE_SCENARIO_ID, factors)

    path = _live_graph_path()
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "live graph not built; run "
                "`uv run python -m riskweave.graph.build_live --snapshot-id <id>` "
                "to assemble it from an ingestion snapshot. The CRE fixture "
                "remains available at POST /graph/seed."
            ),
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        graph = load_graph_fixture(path)
    except (GraphAssemblyError, ValueError, OSError) as exc:
        raise HTTPException(
            status_code=500, detail=f"live graph artifact is invalid: {exc}"
        ) from exc

    factors = tuple(
        (f["factor_id"], f["node_id"], f["magnitude"]) for f in payload.get("factors", [])
    )
    if not factors:
        raise HTTPException(
            status_code=500,
            detail="live graph artifact has no seed factors; rebuild with build_live.",
        )

    _register_runnable_scenario(store, graph, GRAPH_LIVE_SCENARIO_ID, factors)
    return _serialize_graph(graph, GRAPH_LIVE_SCENARIO_ID, factors)


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
            "POST /graph/seed serves a reduced, curated CRE fixture (~15 entities) "
            "as the explicit offline/demo-freeze fallback; POST /graph/live serves "
            "the full universe assembled live from a real ingestion snapshot.",
            "Live edge weights are deterministic-method outputs (Gemini finds the "
            "disclosed sentence; registered DER-* code turns it into the number). "
            "Live relationships currently derive via DER-CONCENTRATION from "
            "disclosed magnitudes; XBRL/FRED numerator-denominator variants "
            "(DER-CREDIT/GEO/COMMODITY, DER-BETA, DER-DURATION) activate as those "
            "numeric joins are wired.",
            "Analytics only — no price predictions and no buy/sell/hold advice.",
        ],
    )

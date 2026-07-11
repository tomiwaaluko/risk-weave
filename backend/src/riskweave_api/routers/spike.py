"""Spike seed endpoint for the Cytoscape.js 200-node visualization spike (RIS-15).

Registers a synthetic 200-node graph snapshot + scenario with the in-memory
ScenarioStore so the existing ``/scenarios/{id}/run`` REST endpoint and
the WebSocket slider work without the full ingestion pipeline.

The synthetic graph reuses the same parameters as bench_propagation.py
(200 nodes, out-degree 7, 5 shock factors) with deterministic seeding.
"""

from __future__ import annotations

import random
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from riskweave.propagation import (
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)
from riskweave_api.dependencies import get_store
from riskweave_api.models import ScenarioCreateRequest, ScenarioState, ShockFactorIn
from riskweave_api.scenario_store import ScenarioStore

router = APIRouter(prefix="/spike", tags=["spike"])
StoreDependency = Annotated[ScenarioStore, Depends(get_store)]

# ---------------------------------------------------------------------------
# Synthetic graph parameters (match bench_propagation.py)
# ---------------------------------------------------------------------------

N_NODES = 200
OUT_DEGREE = 7
N_FACTORS = 5
SEED = 20260711

SPIKE_SNAPSHOT_ID = "spike-snap"
SPIKE_GRAPH_VERSION = "spike-v1"
SPIKE_SCENARIO_ID = "spike-scenario"

NODE_TYPES = ("company", "bank", "reit", "security", "commodity", "geography", "sector")

# Representative entity names by type for a readable spike graph.
_ENTITY_NAMES: dict[str, list[str]] = {
    "company": [
        "Vornado Realty",
        "Simon Property",
        "Boston Properties",
        "SL Green",
        "Mack-Cali",
        "Brookfield Asset",
        "Prologis",
        "Digital Realty",
        "Equinix",
        "American Tower",
        "Crown Castle",
        "Iron Mountain",
        "Welltower",
        "Ventas",
        "Healthpeak",
        "Medical Properties",
        "Realty Income",
        "National Retail",
        "Regency Centers",
        "Federal Realty",
        "Alexandria RE",
        "Kilroy Realty",
        "Cousins Properties",
        "Piedmont Office",
        "Paramount Group",
        "Empire State Realty",
        "RXR Realty",
        "Tishman Speyer",
        "Hines",
        "Related Companies",
    ],
    "bank": [
        "JPMorgan Chase",
        "Bank of America",
        "Wells Fargo",
        "Citigroup",
        "Goldman Sachs",
        "Morgan Stanley",
        "US Bancorp",
        "PNC Financial",
        "Truist Financial",
        "Capital One",
        "TD Bank",
        "Citizens Financial",
        "M&T Bank",
        "Fifth Third",
        "Regions Financial",
        "Huntington Bancshares",
        "KeyCorp",
        "Zions Bancorp",
        "Comerica",
        "SVB Financial",
        "First Republic",
        "Signature Bank",
        "New York Community",
        "Valley National",
        "Webster Financial",
        "Cullen/Frost",
        "Glacier Bancorp",
        "Columbia Banking",
    ],
    "reit": [
        "AvalonBay",
        "Equity Residential",
        "Essex Property",
        "UDR Inc",
        "Camden Property",
        "Mid-America Apartment",
        "Independence Realty",
        "Apartment Investment",
        "NexPoint Residential",
        "Elme Communities",
        "Agree Realty",
        "Spirit Realty",
        "STORE Capital",
        "Broadstone Net Lease",
    ],
    "security": [
        "UST 10Y",
        "UST 2Y",
        "UST 30Y",
        "TIPS 10Y",
        "IG Corp Bond ETF",
        "HY Corp Bond ETF",
        "MBS ETF",
        "CMBS AAA",
        "CMBS BBB",
        "CLO AAA",
        "CLO BB",
    ],
    "commodity": [
        "WTI Crude",
        "Brent Crude",
        "Natural Gas",
        "Gold",
        "Copper",
        "Lumber",
        "Steel HRC",
        "Aluminum",
    ],
    "geography": [
        "New York Metro",
        "Los Angeles",
        "Chicago",
        "San Francisco",
        "Boston",
        "Washington DC",
        "Dallas-Fort Worth",
        "Houston",
        "Miami",
        "Seattle",
        "Denver",
        "Atlanta",
        "Philadelphia",
        "Minneapolis",
        "Phoenix",
        "Austin",
    ],
    "sector": [
        "Commercial Real Estate",
        "Residential Real Estate",
        "Office REIT",
        "Retail REIT",
        "Industrial REIT",
        "Healthcare REIT",
        "Financial Services",
        "Energy",
        "Technology",
        "Insurance",
    ],
}

DERIVATION_METHODS = (
    "DER-CREDIT",
    "DER-CONCENTRATION",
    "DER-COMMODITY",
    "DER-DURATION",
    "DER-GEO",
    "DER-BETA",
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SpikeNodeOut(BaseModel):
    node_id: str
    node_type: str
    name: str


class SpikeEdgeOut(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    weight: float
    method_id: str
    provenance_ref: str


class SpikePathOut(BaseModel):
    path_key: str
    factor_id: str
    target_node_id: str
    hop_count: int
    contribution: float
    edge_ids: list[str]
    method_ids: list[str]
    provenance_refs: list[str]


class SpikeNodeImpactOut(BaseModel):
    node_id: str
    raw_impact: float
    risk_score: float
    contributions: list[SpikePathOut]


class SpikeSeedResponse(BaseModel):
    scenario_id: str
    snapshot_id: str
    graph_version: str
    state: str
    nodes: list[SpikeNodeOut]
    edges: list[SpikeEdgeOut]
    factors: list[dict[str, Any]]


class SpikeRunResponse(BaseModel):
    scenario_id: str
    severity: float
    impacts: dict[str, SpikeNodeImpactOut]
    ranked_entity_ids: list[str]
    latency_ms: float
    cached: bool


# ---------------------------------------------------------------------------
# Synthetic graph builder
# ---------------------------------------------------------------------------


def _build_synthetic_graph() -> tuple[
    tuple[GraphNode, ...],
    tuple[GraphEdge, ...],
    tuple[ShockFactor, ...],
]:
    """Build a deterministic 200-node synthetic graph with representative structure."""
    rng = random.Random(SEED)

    # Assign names round-robin within each type.
    type_counters: dict[str, int] = {t: 0 for t in NODE_TYPES}
    nodes: list[GraphNode] = []
    for i in range(N_NODES):
        node_type = NODE_TYPES[i % len(NODE_TYPES)]
        names = _ENTITY_NAMES[node_type]
        name_idx = type_counters[node_type] % len(names)
        name = names[name_idx]
        if type_counters[node_type] >= len(names):
            name = f"{name} {type_counters[node_type] // len(names) + 1}"
        type_counters[node_type] += 1
        nodes.append(GraphNode(node_id=f"n{i}", node_type=node_type, name=name))

    edges: list[GraphEdge] = []
    edge_id = 0
    for i in range(N_NODES):
        targets = rng.sample([j for j in range(N_NODES) if j != i], OUT_DEGREE)
        source_type = nodes[i].node_type
        for j in targets:
            # Pick a derivation method that makes sense for the source type.
            if source_type == "commodity":
                method = "DER-COMMODITY"
            elif source_type == "geography":
                method = "DER-GEO"
            elif source_type in ("bank", "company", "reit"):
                method = rng.choice(["DER-CREDIT", "DER-CONCENTRATION", "DER-DURATION"])
            else:
                method = rng.choice(list(DERIVATION_METHODS))

            edges.append(
                GraphEdge(
                    edge_id=f"e{edge_id}",
                    source_id=f"n{i}",
                    target_id=f"n{j}",
                    weight=rng.uniform(0.05, 0.9),
                    method_id=method,
                    provenance_ref=f"prov:spike:e{edge_id}",
                )
            )
            edge_id += 1

    # Shock factors: pick hub nodes (banks, central geography).
    factor_origins = [0, 11, 22, 33, 44]  # Spread across entity types
    factors = tuple(
        ShockFactor(
            factor_id=f"spike-f{k}",
            node_id=f"n{factor_origins[k]}",
            magnitude=1.0 + k * 0.25,
        )
        for k in range(N_FACTORS)
    )

    return tuple(nodes), tuple(edges), factors


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/seed", response_model=SpikeSeedResponse, status_code=status.HTTP_201_CREATED)
def seed_spike(
    store: StoreDependency,
) -> SpikeSeedResponse:
    """Create and register a synthetic 200-node graph for the Cytoscape.js spike.

    Idempotent: re-seeding overwrites the previous spike scenario.
    """
    nodes, edges, factors = _build_synthetic_graph()

    snapshot = GraphSnapshot(
        snapshot_id=SPIKE_SNAPSHOT_ID,
        graph_version=SPIKE_GRAPH_VERSION,
        nodes=nodes,
        edges=edges,
    )
    store.register_snapshot(snapshot)

    # Remove any previous spike scenario so re-seeding works.
    with store._lock:
        store._records.pop(SPIKE_SCENARIO_ID, None)
        store._configs.pop(SPIKE_SCENARIO_ID, None)

    req = ScenarioCreateRequest(
        scenario_id=SPIKE_SCENARIO_ID,
        snapshot_id=SPIKE_SNAPSHOT_ID,
        graph_version=SPIKE_GRAPH_VERSION,
        factors=[
            ShockFactorIn(
                factor_id=f.factor_id,
                node_id=f.node_id,
                magnitude=f.magnitude,
            )
            for f in factors
        ],
        seed=SEED,
    )
    store.create(req)

    # Auto-transition to READY so it's immediately runnable.
    store.transition(SPIKE_SCENARIO_ID, ScenarioState.VALIDATING)
    store.transition(SPIKE_SCENARIO_ID, ScenarioState.READY)

    return SpikeSeedResponse(
        scenario_id=SPIKE_SCENARIO_ID,
        snapshot_id=SPIKE_SNAPSHOT_ID,
        graph_version=SPIKE_GRAPH_VERSION,
        state=ScenarioState.READY,
        nodes=[SpikeNodeOut(node_id=n.node_id, node_type=n.node_type, name=n.name) for n in nodes],
        edges=[
            SpikeEdgeOut(
                edge_id=e.edge_id,
                source_id=e.source_id,
                target_id=e.target_id,
                weight=e.weight,
                method_id=e.method_id,
                provenance_ref=e.provenance_ref,
            )
            for e in edges
        ],
        factors=[
            {"factor_id": f.factor_id, "node_id": f.node_id, "magnitude": f.magnitude}
            for f in factors
        ],
    )


@router.post("/run", response_model=SpikeRunResponse)
def run_spike(
    store: StoreDependency,
    severity: float = 1.0,
) -> SpikeRunResponse:
    """Run propagation on the spike scenario at the given severity.

    This is a convenience endpoint that bypasses the full scenario lifecycle
    for the spike. The frontend also uses the WebSocket slider, but this
    endpoint is useful for testing and initial load.
    """
    import time

    try:
        record = store.get(SPIKE_SCENARIO_ID)
        snapshot = store.get_snapshot(record.snapshot_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Spike not seeded — call POST /spike/seed first",
        ) from exc

    scaled = Scenario(
        scenario_id=record.scenario.scenario_id,
        factors=tuple(
            ShockFactor(
                factor_id=f.factor_id,
                node_id=f.node_id,
                magnitude=f.magnitude * severity,
            )
            for f in record.scenario.factors
        ),
        seed=record.scenario.seed,
    )

    t0 = time.perf_counter()
    result = propagate(snapshot, scaled)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    ranked = result.ranked_entities()
    impacts: dict[str, SpikeNodeImpactOut] = {}
    for ni in ranked:
        paths = [
            SpikePathOut(
                path_key=pc.path_key,
                factor_id=pc.factor_id,
                target_node_id=pc.target_node_id,
                hop_count=pc.hop_count,
                contribution=pc.contribution,
                edge_ids=[e.edge_id for e in pc.edges],
                method_ids=[e.method_id for e in pc.edges],
                provenance_refs=[e.provenance_ref for e in pc.edges],
            )
            for pc in ni.contributions
        ]
        impacts[ni.node_id] = SpikeNodeImpactOut(
            node_id=ni.node_id,
            raw_impact=ni.raw_impact,
            risk_score=ni.risk_score,
            contributions=paths,
        )

    return SpikeRunResponse(
        scenario_id=SPIKE_SCENARIO_ID,
        severity=severity,
        impacts=impacts,
        ranked_entity_ids=[ni.node_id for ni in ranked],
        latency_ms=latency_ms,
        cached=False,
    )

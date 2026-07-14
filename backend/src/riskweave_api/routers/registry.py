"""§13.2 deterministic tool registry endpoints (RW-SEC-001/002).

These are the closed set of functions Gemini orchestration may call later.
Nothing outside this list gets exposed. Breach-distance and duration stubs
are included; they return NotImplemented until the grafts land (RIS-17).

Functions: resolve_entity, get_company_exposures, run_scenario,
           propagate_shock, get_propagation_paths, get_ratio,
           retrieve_filing_passage, retrieve_fred_series.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from riskweave.entity_resolution import Resolver
from riskweave_api.dependencies import get_store
from riskweave_api.models import (
    CompanyExposuresResponse,
    FilingPassageResponse,
    FredSeriesResponse,
    PropagateShockResponse,
    PropagationPathsResponse,
    RatioResponse,
    ResolveEntityRequest,
    ResolveEntityResponse,
    RunRequest,
)
from riskweave_api.scenario_store import NotFoundError, ScenarioStore
from riskweave_api.security import default_rate_limit

router = APIRouter(
    prefix="/registry", tags=["registry"], dependencies=[Depends(default_rate_limit)]
)
REPO_ROOT = Path(__file__).resolve().parents[4]


@lru_cache(maxsize=1)
def _curated_resolver() -> Resolver | None:
    candidates = []
    configured_path = os.environ.get("RISKWEAVE_UNIVERSE_PATH")
    if configured_path:
        candidates.append(Path(configured_path))
    candidates.extend(
        [
            REPO_ROOT / "data/universe/entities.json",
            Path("/app/data/universe/entities.json"),
        ]
    )
    for path in candidates:
        if path.exists():
            return Resolver.from_universe_file(path)
    return None


@router.post("/resolve_entity", response_model=ResolveEntityResponse)
def resolve_entity(
    req: ResolveEntityRequest,
    store: ScenarioStore = Depends(get_store),
) -> ResolveEntityResponse:
    """Find the canonical node id for a natural-language entity name.

    RIS-11 deterministic universe resolution runs first. Registered snapshots
    remain as a compatibility fallback for test/demo snapshots not in the
    curated universe.
    """
    resolver = _curated_resolver()
    if resolver is not None:
        result = resolver.resolve(req.query)
        if result.entity is not None:
            return ResolveEntityResponse(
                node_id=result.entity.id,
                name=result.entity.canonical_name,
                node_type=result.entity.entity_type,
            )

    query = req.query.strip().lower()
    for snapshot in store._snapshots.values():
        for node in snapshot.nodes:
            if node.name.lower().startswith(query) or query in node.name.lower():
                return ResolveEntityResponse(
                    node_id=node.node_id,
                    name=node.name,
                    node_type=node.node_type,
                )
    return ResolveEntityResponse(node_id=None, name=None, node_type=None)


@router.get("/company_exposures/{node_id}", response_model=CompanyExposuresResponse)
def get_company_exposures(
    node_id: str,
    snapshot_id: str,
    store: ScenarioStore = Depends(get_store),
) -> CompanyExposuresResponse:
    """Return outgoing edges (with provenance) for a node in a snapshot."""
    try:
        snapshot = store.get_snapshot(snapshot_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot not found") from exc

    if not snapshot.has_node(node_id):
        raise HTTPException(status_code=404, detail="node not found")

    edges = [
        {
            "edge_id": e.edge_id,
            "target_id": e.target_id,
            "weight": e.weight,
            "method_id": e.method_id,
            "provenance_ref": e.provenance_ref,
        }
        for e in snapshot.outgoing(node_id)
    ]
    return CompanyExposuresResponse(node_id=node_id, outgoing_edges=edges)


@router.post("/run_scenario/{scenario_id}", response_model=PropagateShockResponse)
async def run_scenario_registry(
    scenario_id: str,
    body: RunRequest = RunRequest(),
    store: ScenarioStore = Depends(get_store),
) -> PropagateShockResponse:
    """Run a registered scenario and return the propagation result."""
    try:
        run_result, _ = store.run(scenario_id, body.severity)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="scenario not found") from exc
    return PropagateShockResponse(result=run_result)


@router.post("/propagate_shock/{scenario_id}", response_model=PropagateShockResponse)
async def propagate_shock(
    scenario_id: str,
    body: RunRequest = RunRequest(),
    store: ScenarioStore = Depends(get_store),
) -> PropagateShockResponse:
    """Alias of run_scenario for Gemini tool registry (`propagate_shock`)."""
    return await run_scenario_registry(scenario_id, body, store)


@router.get("/propagation_paths/{scenario_id}/{node_id}", response_model=PropagationPathsResponse)
async def get_propagation_paths(
    scenario_id: str,
    node_id: str,
    severity: float = 1.0,
    store: ScenarioStore = Depends(get_store),
) -> PropagationPathsResponse:
    """Return all retained paths reaching node_id in a scenario run."""
    try:
        run_result, _ = store.run(scenario_id, severity)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="scenario not found") from exc

    impact = run_result.impacts.get(node_id)
    if impact is None:
        raise HTTPException(status_code=404, detail="node not impacted or not found")
    return PropagationPathsResponse(paths=impact.contributions)


@router.get("/ratio/{snapshot_id}/{node_id}/{method_id}", response_model=RatioResponse)
def get_ratio(
    snapshot_id: str,
    node_id: str,
    method_id: str,
    store: ScenarioStore = Depends(get_store),
) -> RatioResponse:
    """Return a pre-derived ratio for an entity (stub: returns placeholder)."""
    try:
        store.get_snapshot(snapshot_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot not found") from exc
    # Stub: real values come from the derivation registry (RIS-11/12 data)
    return RatioResponse(
        method_id=method_id,
        value=0.0,
        provenance_ref="stub:not-yet-derived",
    )


@router.get("/filing_passage/{document_id}", response_model=FilingPassageResponse)
def retrieve_filing_passage(
    document_id: str,
    char_start: int = 0,
    char_end: int = 100,
) -> FilingPassageResponse:
    """Retrieve an exact quoted passage from a filing (stub until ingestion lands)."""
    return FilingPassageResponse(
        source_document_id=document_id,
        passage="[stub: ingestion pipeline not yet wired]",
        char_start=char_start,
        char_end=char_end,
    )


@router.get("/fred_series/{series_id}", response_model=FredSeriesResponse)
def retrieve_fred_series(series_id: str) -> FredSeriesResponse:
    """Retrieve a FRED time series (stub until ingestion lands)."""
    return FredSeriesResponse(series_id=series_id, values=[])


@router.get("/breach_distance/{scenario_id}/{node_id}")
def breach_distance(scenario_id: str, node_id: str) -> dict:
    """Stub: breach-distance graft (RIS-17, RW-ALG-030) not yet implemented."""
    return {"status": "not_implemented", "graft": "breach-distance", "ticket": "RIS-17"}


@router.get("/duration_transmission/{scenario_id}/{node_id}")
def duration_transmission(scenario_id: str, node_id: str) -> dict:
    """Stub: duration-based rate transmission (RIS-17, RW-ALG-031) not yet implemented."""
    return {"status": "not_implemented", "graft": "duration", "ticket": "RIS-17"}

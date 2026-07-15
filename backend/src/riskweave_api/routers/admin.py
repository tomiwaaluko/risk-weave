"""Guarded operational endpoints to run the live pipeline (RIS-28).

These endpoints run the RIS-10 extraction pass and RIS-9/11/12 assembly over a
frozen ingestion snapshot from a normal (web-server) deployment, so a long
extraction survives as a background task while ``/health`` keeps the container
alive — unlike a one-off whose healthcheck would kill it.

**Security.** The whole router is disabled (404) unless ``RISKWEAVE_ADMIN_TOKEN``
is set; when set, every call must present a matching ``X-Admin-Token`` header
(constant-time compared). It is never open by default, and it triggers only the
fixed diagnose/extract/build operations — no arbitrary input is executed.
"""

from __future__ import annotations

import secrets
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from riskweave.graph.build_live import SnapshotNotFoundError, assemble_live_from_db
from riskweave_api.ingestion.database import session_factory
from riskweave_api.ingestion.pipeline import ExtractionProgress, diagnose, run_extraction

router = APIRouter(prefix="/admin/pipeline", tags=["admin"])


def require_admin(
    request: Request,
    x_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    """Gate: 404 when the feature is off, 403 on a bad/absent token."""
    token = request.app.state.settings.admin_token
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="admin endpoints are disabled"
        )
    presented = x_admin_token or ""
    if not secrets.compare_digest(presented, token.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid or missing admin token"
        )


def _pipeline_state(request: Request) -> dict[str, Any]:
    state = getattr(request.app.state, "pipeline", None)
    if state is None:
        state = {
            "lock": threading.Lock(),
            "status": {"running": False, "finished": False, "error": None, "progress": None},
        }
        request.app.state.pipeline = state
    return state


@router.post("/diagnose", dependencies=[Depends(require_admin)])
def admin_diagnose(request: Request, snapshot_id: int) -> dict[str, Any]:
    """Report snapshot + extraction counts (no Gemini calls)."""
    settings = request.app.state.settings
    try:
        with session_factory(settings.database_url)() as session:
            return diagnose(session, snapshot_id)
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/extract", dependencies=[Depends(require_admin)], status_code=status.HTTP_202_ACCEPTED
)
def admin_extract(request: Request, snapshot_id: int, limit: int | None = None) -> dict[str, Any]:
    """Start the extraction pass as a background task (resumable, idempotent)."""
    settings = request.app.state.settings
    state = _pipeline_state(request)
    if not state["lock"].acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="an extraction run is already in progress"
        )

    status_obj: dict[str, Any] = {
        "running": True,
        "finished": False,
        "error": None,
        "snapshot_id": snapshot_id,
        "limit": limit,
        "progress": None,
    }
    state["status"] = status_obj
    api_key = settings.gemini_api_key
    database_url = settings.database_url

    def _worker() -> None:
        try:
            with session_factory(database_url)() as session:

                def _progress(p: ExtractionProgress) -> None:
                    status_obj["progress"] = p.as_dict()

                run_extraction(
                    session, snapshot_id, api_key=api_key, limit=limit, progress=_progress
                )
            status_obj["finished"] = True
        except Exception as exc:  # record and surface via /status
            status_obj["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            status_obj["running"] = False
            state["lock"].release()

    threading.Thread(target=_worker, name="riskweave-extract", daemon=True).start()
    return {"started": True, "snapshot_id": snapshot_id, "limit": limit}


@router.get("/status", dependencies=[Depends(require_admin)])
def admin_status(request: Request) -> dict[str, Any]:
    """Report the current/last extraction run's progress."""
    return _pipeline_state(request)["status"]


@router.post("/build", dependencies=[Depends(require_admin)])
def admin_build(
    request: Request, snapshot_id: int, graph_version: str = "live-1.0.0"
) -> dict[str, Any]:
    """Assemble the live graph from stored extractions and report its stats."""
    settings = request.app.state.settings
    try:
        with session_factory(settings.database_url)() as session:
            result, snapshot = assemble_live_from_db(
                session, snapshot_id=snapshot_id, graph_version=graph_version
            )
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    report = result.report
    return {
        "snapshot_id": snapshot.id,
        "snapshot_name": snapshot.name,
        "graph_snapshot_id": result.graph.snapshot_id,
        "graph_version": result.graph.graph_version,
        "checksum": result.graph.checksum,
        "node_count": len(result.graph.entities),
        "edge_count": len(result.graph.edges),
        "relationships_seen": report.relationships_seen,
        "edges_built": report.edges_built,
        "entity_coverage": report.entity_coverage,
        "resolution_layers": dict(report.resolution_layers),
        "drops_by_reason": dict(report.drops_by_reason),
        "default_factors": [
            {"factor_id": fid, "node_id": nid, "magnitude": mag}
            for fid, nid, mag in result.default_factors
        ],
    }

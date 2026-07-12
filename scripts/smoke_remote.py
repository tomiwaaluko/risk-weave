#!/usr/bin/env python3
"""External smoke test for a live RiskWeave backend (RIS-25 acceptance).

Exercises the always-on deployment end to end from outside the cluster:

  1. GET  /health                         -> liveness + reported status
  2. POST /graph/seed                      -> load the committed fixture graph
                                              (15 nodes / 18 edges) and register
                                              the runnable ``cre-demo`` scenario;
                                              this path needs no live ingestion
  3. POST /registry/run_scenario/cre-demo  -> one deterministic propagation run
  4. WSS  /scenarios/cre-demo/slider       -> severity-slider round-trip, twice
                                              (second send should be cache-warm)

Run it from a network that can reach *.up.railway.app (the CI sandbox's egress
policy blocks that host, so this cannot run from inside the agent environment):

    uv run python scripts/smoke_remote.py
    uv run python scripts/smoke_remote.py https://backend-production-b2dc.up.railway.app

The HTTP steps use only the standard library. The WebSocket step needs the
``websockets`` package (``uv run --with websockets python scripts/smoke_remote.py``
or ``pip install websockets``); if it is missing the script still runs steps 1-3
and reports the WS step as skipped.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://backend-production-b2dc.up.railway.app"
SCENARIO_ID = "cre-demo"
HTTP_TIMEOUT = 30


class SmokeFailure(Exception):
    """A verification step failed."""


def _post(url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else b"{}"
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


def _get(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


def check_health(base: str) -> None:
    status, body = _get(f"{base}/health")
    if status != 200:
        raise SmokeFailure(f"/health returned HTTP {status}")
    print(f"  [1] /health              HTTP {status}  {json.dumps(body)}")


def check_seed(base: str) -> None:
    status, body = _post(f"{base}/graph/seed")
    if status not in (200, 201):
        raise SmokeFailure(f"/graph/seed returned HTTP {status}")
    nodes = len(body.get("nodes", []))
    edges = len(body.get("edges", []))
    if body.get("scenario_id") != SCENARIO_ID or nodes == 0 or edges == 0:
        raise SmokeFailure(f"/graph/seed payload unexpected: {json.dumps(body)[:200]}")
    print(
        f"  [2] /graph/seed          HTTP {status}  "
        f"scenario={body['scenario_id']} state={body.get('state')} "
        f"nodes={nodes} edges={edges}"
    )


def check_run(base: str) -> None:
    status, body = _post(f"{base}/registry/run_scenario/{SCENARIO_ID}", {"severity": 0.8})
    if status != 200:
        raise SmokeFailure(f"/registry/run_scenario returned HTTP {status}")
    result = body.get("result", {})
    ranked = result.get("ranked_entity_ids", [])
    if not ranked:
        raise SmokeFailure("propagation returned no ranked entities")
    top = ranked[0]
    top_score = result.get("impacts", {}).get(top, {}).get("risk_score")
    print(
        f"  [3] run_scenario         HTTP {status}  "
        f"severity=0.8 ranked={len(ranked)} top={top} risk_score={top_score} "
        f"latency_ms={result.get('latency_ms')}"
    )


def check_slider(base: str) -> bool:
    try:
        import asyncio

        import websockets
    except ImportError:
        print(
            "  [4] slider WSS           SKIPPED (install `websockets`: "
            "uv run --with websockets python scripts/smoke_remote.py)"
        )
        return True

    ws_url = base.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/scenarios/{SCENARIO_ID}/slider"

    async def _roundtrip() -> None:
        async with websockets.connect(ws_url, open_timeout=HTTP_TIMEOUT) as ws:
            for severity in (0.45, 0.45):
                await ws.send(json.dumps({"severity": severity}))
                raw = await ws.recv()
                msg = json.loads(raw)
                if "error" in msg:
                    raise SmokeFailure(f"slider error: {msg['error']}")
                if msg.get("severity") != severity:
                    raise SmokeFailure(
                        f"slider echoed severity {msg.get('severity')} != {severity}"
                    )
                ranked = len(msg.get("ranked_entity_ids", []))
                print(
                    f"  [4] slider WSS           frame ok   "
                    f"severity={msg['severity']} cached={msg.get('cached')} "
                    f"latency_ms={msg.get('latency_ms')} ranked={ranked}"
                )

    asyncio.run(_roundtrip())
    return True


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL).rstrip("/")
    print(f"RiskWeave remote smoke test against {base}\n")
    try:
        check_health(base)
        check_seed(base)
        check_run(base)
        check_slider(base)
    except SmokeFailure as exc:
        print(f"\nFAIL: {exc}")
        return 1
    except urllib.error.HTTPError as exc:
        print(f"\nFAIL: HTTP {exc.code} from {exc.url}: {exc.read()[:200]!r}")
        return 1
    except Exception as exc:  # noqa: BLE001 - surface any transport error clearly
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return 1
    print("\nPASS: all reachable checks succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

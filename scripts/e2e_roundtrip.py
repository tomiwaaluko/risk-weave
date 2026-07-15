#!/usr/bin/env python3
"""Deterministic end-to-end round-trip against a running RiskWeave stack (RIS-36).

Boots nothing itself: it drives an already-running backend (the CI ``e2e`` job
brings the Docker Compose stack up first) through the committed, Gemini-free
demo path and asserts the propagation result is bit-stable:

  1. GET  /health                          -> liveness
  2. POST /graph/seed                       -> load the committed CRE fixture graph
                                               and register the ``cre-demo`` scenario
                                               (no live ingestion, no Gemini call)
  3. POST /registry/run_scenario/cre-demo   -> one deterministic propagation run,
                                               done twice to prove reproducibility
                                               (RW-PRIN-009)

The run result is normalized (the non-deterministic ``latency_ms`` dropped,
floats rounded) and hashed. The hash is asserted against a committed golden so a
silent change in a derivation weight, the fixture graph, or the engine fails CI
instead of shipping. Run explicitly with::

    uv run python scripts/e2e_roundtrip.py                       # localhost:8000
    uv run python scripts/e2e_roundtrip.py http://localhost:8000

Override the golden (e.g. after an intended engine change) with
``--expected <sha256>`` or ``RISKWEAVE_E2E_EXPECTED_HASH``; pass ``--print-hash``
to compute and print the current hash without asserting.

The HTTP steps use only the standard library so the script has no dependencies
beyond a Python interpreter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:8000"
SCENARIO_ID = "cre-demo"
HTTP_TIMEOUT = 30
# Full-severity canonical run; the golden below is pinned to this severity.
SEVERITY = 1.0
FLOAT_PRECISION = 6

# Committed replay identity of the fixture graph (see docs/demo/FROZEN_DEMO_BUNDLE.json).
EXPECTED_SNAPSHOT_ID = "cre-demo-2026-07-11"
EXPECTED_GRAPH_VERSION = "1.0.0"

# sha256 of the normalized severity=1.0 propagation result. Regenerate with
# ``--print-hash`` after an intended, reviewed change to the engine or fixture.
EXPECTED_RESULT_HASH = "1a79cebc08e5f203091f075862be6ca5b956e015c761340d98230e316078297a"


class RoundTripFailure(Exception):
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


def _round_floats(obj: object, ndigits: int = FLOAT_PRECISION) -> object:
    """Round every float in a nested JSON structure to tame last-ULP noise."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def normalize_result(result: dict) -> dict:
    """Drop the non-deterministic latency and round floats for stable hashing."""
    stable = {k: v for k, v in result.items() if k != "latency_ms"}
    return _round_floats(stable)  # type: ignore[return-value]


def result_hash(result: dict) -> str:
    canonical = json.dumps(normalize_result(result), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def wait_for_health(base: str, attempts: int = 30, delay: float = 2.0) -> None:
    """Poll /health until ready. Compose ``--wait`` should already guarantee this."""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            status, body = _get(f"{base}/health")
            if status == 200 and body.get("status") == "ok":
                print(f"  [1] /health              HTTP {status}  {json.dumps(body)}")
                return
            last = RoundTripFailure(f"/health returned HTTP {status} {body}")
        except (urllib.error.URLError, ConnectionError) as exc:  # not up yet
            last = exc
        time.sleep(delay)
    raise RoundTripFailure(f"backend never became healthy: {last}")


def seed_graph(base: str) -> None:
    status, body = _post(f"{base}/graph/seed")
    if status not in (200, 201):
        raise RoundTripFailure(f"/graph/seed returned HTTP {status}")
    if body.get("scenario_id") != SCENARIO_ID:
        raise RoundTripFailure(f"/graph/seed scenario_id={body.get('scenario_id')!r}")
    if body.get("snapshot_id") != EXPECTED_SNAPSHOT_ID:
        raise RoundTripFailure(
            f"/graph/seed snapshot_id={body.get('snapshot_id')!r} "
            f"!= {EXPECTED_SNAPSHOT_ID!r}"
        )
    if body.get("graph_version") != EXPECTED_GRAPH_VERSION:
        raise RoundTripFailure(
            f"/graph/seed graph_version={body.get('graph_version')!r} "
            f"!= {EXPECTED_GRAPH_VERSION!r}"
        )
    nodes, edges = len(body.get("nodes", [])), len(body.get("edges", []))
    if nodes == 0 or edges == 0:
        raise RoundTripFailure("/graph/seed returned an empty graph")
    print(
        f"  [2] /graph/seed          HTTP {status}  "
        f"snapshot={body['snapshot_id']} checksum={body.get('checksum')} "
        f"nodes={nodes} edges={edges}"
    )


def run_once(base: str) -> dict:
    status, body = _post(
        f"{base}/registry/run_scenario/{SCENARIO_ID}", {"severity": SEVERITY}
    )
    if status != 200:
        raise RoundTripFailure(f"/registry/run_scenario returned HTTP {status}")
    result = body.get("result")
    if not result or not result.get("ranked_entity_ids"):
        raise RoundTripFailure("propagation returned no ranked entities")
    return result


def run_roundtrip(base: str, expected: str, *, assert_hash: bool) -> str:
    wait_for_health(base)
    seed_graph(base)

    first, second = run_once(base), run_once(base)
    hash_first, hash_second = result_hash(first), result_hash(second)
    if hash_first != hash_second:
        raise RoundTripFailure(
            f"non-deterministic run: {hash_first} != {hash_second}"
        )
    top = first["ranked_entity_ids"][0]
    top_score = first["impacts"][top]["risk_score"]
    print(
        f"  [3] run_scenario x2      HTTP 200  severity={SEVERITY} "
        f"ranked={len(first['ranked_entity_ids'])} top={top} risk_score={top_score}"
    )
    print(f"  [=] result hash          {hash_first}")

    if assert_hash and hash_first != expected:
        raise RoundTripFailure(
            f"result hash {hash_first} != expected {expected}; "
            "regenerate with --print-hash if this change is intended"
        )
    return hash_first


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--expected",
        default=os.environ.get("RISKWEAVE_E2E_EXPECTED_HASH", EXPECTED_RESULT_HASH),
        help="golden sha256 to assert against",
    )
    parser.add_argument(
        "--print-hash",
        action="store_true",
        help="print the current hash without asserting the golden",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"RiskWeave deterministic e2e round-trip against {base}\n")
    try:
        computed = run_roundtrip(base, args.expected, assert_hash=not args.print_hash)
    except RoundTripFailure as exc:
        print(f"\nFAIL: {exc}")
        return 1
    except urllib.error.HTTPError as exc:
        print(f"\nFAIL: HTTP {exc.code} from {exc.url}: {exc.read()[:200]!r}")
        return 1
    except Exception as exc:  # noqa: BLE001 - surface any transport error clearly
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return 1

    if args.print_hash:
        print(f"\n{computed}")
    else:
        print("\nPASS: deterministic round-trip matched the committed golden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

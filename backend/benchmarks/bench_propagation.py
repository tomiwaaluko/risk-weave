"""Propagation benchmark on a full-size curated graph (RIS-13, `RW-NFR-002`).

Builds a deterministic synthetic graph at the top of the curated-universe range
(200 nodes, ~3.5% edge density mimicking the pack structure) and times repeated
recomputes of a five-factor scenario — the slider-drag access pattern the
500 ms budget applies to downstream.

Run:  python -m benchmarks.bench_propagation   (from backend/)
"""

from __future__ import annotations

import random
import statistics
import time

from riskweave.propagation import (
    ENGINE_VERSION,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)

N_NODES = 200
OUT_DEGREE = 7  # hub-and-spoke curated graph: banks/commodities fan out
N_FACTORS = 5  # RW-FR-006 minimum simultaneous factors
N_RUNS = 100
SEED = 20260711


def build_snapshot() -> GraphSnapshot:
    rng = random.Random(SEED)
    types = ["company", "bank", "reit", "security", "commodity", "geography", "sector"]
    nodes = tuple(
        GraphNode(node_id=f"n{i}", node_type=types[i % len(types)], name=f"Entity {i}")
        for i in range(N_NODES)
    )
    edges = []
    edge_id = 0
    for i in range(N_NODES):
        targets = rng.sample([j for j in range(N_NODES) if j != i], OUT_DEGREE)
        for j in targets:
            edges.append(
                GraphEdge(
                    edge_id=f"e{edge_id}",
                    source_id=f"n{i}",
                    target_id=f"n{j}",
                    weight=rng.uniform(0.05, 0.9),
                    method_id="DER-CREDIT",
                    provenance_ref=f"prov:e{edge_id}",
                )
            )
            edge_id += 1
    return GraphSnapshot(
        snapshot_id="bench-snap",
        graph_version="bench",
        nodes=nodes,
        edges=tuple(edges),
    )


def main() -> None:
    snap = build_snapshot()
    scenario = Scenario(
        scenario_id="bench-scn",
        factors=tuple(
            ShockFactor(factor_id=f"f{k}", node_id=f"n{k * 11}", magnitude=1.0 + k * 0.25)
            for k in range(N_FACTORS)
        ),
    )

    propagate(snap, scenario)  # warm-up

    timings_ms = []
    for _ in range(N_RUNS):
        start = time.perf_counter()
        result = propagate(snap, scenario)
        timings_ms.append((time.perf_counter() - start) * 1000.0)

    n_paths = sum(len(ni.contributions) for ni in result.impacts.values())
    timings_ms.sort()
    print(f"engine_version={ENGINE_VERSION}")
    print(f"graph: {N_NODES} nodes, {len(snap.edges)} edges; scenario: {N_FACTORS} factors")
    print(f"impacted nodes: {len(result.impacts)}; retained paths: {n_paths}")
    print(
        f"propagate() over {N_RUNS} runs: "
        f"median {statistics.median(timings_ms):.2f} ms, "
        f"p95 {timings_ms[int(0.95 * N_RUNS) - 1]:.2f} ms, "
        f"max {timings_ms[-1]:.2f} ms"
    )


if __name__ == "__main__":
    main()

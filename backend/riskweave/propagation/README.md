# Deterministic propagation engine (`RIS-13`)

Implements ADR-001 exactly (`RW-ALG-005/006`, `RW-FR-017/018`): simple-path
contribution tracking with geometric hop damping.

```
path_contribution(p) = shock_magnitude × Π edge_weight(eᵢ) × 0.60^(h−1)   h ∈ 1..3
raw_node_impact      = fsum(retained incoming path contributions)
risk_score           = 100 × (1 − e^(−|raw_node_impact|))
```

- **Cycle handling:** paths are simple — a candidate path that would revisit a
  node is rejected before contributing. No double counting, no traversal loops
  (`test_cycle_does_not_double_count`).
- **Floor:** a path below `0.005` absolute contribution is neither retained nor
  expanded.
- **Decomposable:** every node's `raw_impact` is exactly the sum of its retained
  `PathContribution`s, each carrying ordered edges with weights, method ids, and
  provenance refs for the evidence panel (`RW-ALG-004`).
- **Deterministic:** pure function of `(GraphSnapshot, Scenario)`; adjacency is
  sorted by edge id, aggregation uses `math.fsum` in canonical path-key order.
  The scenario `seed` is recorded in the result for the reproducibility bundle
  but never consumed — there is no randomness to seed.
- **`risk_score` is a bounded display/ranking score, not a probability** and
  must not be labeled as one (ADR-001).

The engine runs on an in-memory `GraphSnapshot` loaded once per scenario —
never per slider tick. A `GraphEdge` is unconstructible without a `method_id`
and `provenance_ref` (Graft 2 upheld at the type level).

## Benchmark (`RW-NFR-002` input)

`python -m benchmarks.bench_propagation` from `backend/`, on a 200-node /
1,400-edge synthetic curated graph with 5 simultaneous factors:
median **3.4 ms**, p95 3.8 ms per full recompute — ~150× headroom against the
500 ms slider budget.

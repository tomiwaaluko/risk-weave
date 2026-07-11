# ADR-001: Propagation Aggregation And Cycle Handling

## Status

Accepted for v1.

## Context

RiskWeave must turn already-derived deterministic edge weights into bounded,
decomposable node impacts. `RW-ALG-005` fixes the constraints: first-order impact
is `shock magnitude * edge weight`, propagation stops below a floor threshold,
depth is capped at three hops, and cycle handling must prevent double counting.
`RW-ALG-006` also requires the node risk score to be bounded and decomposable.

The open design choice is the aggregation formula around those fixed rules. It
must optimize for financial correctness, evidence provenance, explainability,
reproducibility, and reliable demo behavior before performance or extensibility.

## Original Requirement

Choose the exact propagation damping/aggregation formula, floor threshold, and
cycle-handling strategy without weakening `RW-ALG-005`.

## Proposed Change

Adopt simple-path contribution tracking, a three-hop cap, `0.60` hop damping, a
`0.005` floor threshold, and a bounded exponential display score.

## Reason

This is the smallest formula that preserves the first-order requirement, exposes
path-level provenance, prevents cycle double counting, and remains demo-reliable.

## Decision

Use simple-path contribution tracking with geometric hop damping.

For a path `p = e1..eh`, where `h` is 1 to 3:

```text
path_contribution(p) = shock_magnitude * product(edge_weight(ei)) * damping^(h - 1)
```

Use `damping = 0.60`. This preserves the required first-order formula because
`damping^0 = 1`. Stop expanding a path when `abs(path_contribution) < 0.005`
on the normalized scenario-impact scale. Cap traversal at three hops.

Track every contribution by a stable path key:

```text
source_scenario_id + source_factor_id + ordered_edge_id_sequence + target_node_id
```

A path must be simple: no node may appear twice in the same path. If traversal
would revisit a node, do not expand that candidate path. Parallel edges may both
contribute only when they have distinct edge IDs, derivation methods, and
provenance records.

Aggregate node stress as:

```text
raw_node_impact = sum(path_contribution for incoming retained paths)
risk_score = 100 * (1 - exp(-abs(raw_node_impact)))
```

The UI must keep the signed `path_contribution` records for explanation and path
decomposition, while the bounded `risk_score` is only the display/ranking score.

## Alternatives Considered

- Matrix multiplication over the adjacency matrix: compact, but harder to show
  exact path decomposition and easier to double-count cycles unless additional
  bookkeeping is added.
- Max-path aggregation only: avoids double counting, but hides secondary paths
  that judges will expect to inspect.
- No damping: simpler, but overstates third-order contagion and makes the
  three-hop story less defensible.

## Consequences

- Cycle prevention is explicit and testable: paths that revisit a node are
  rejected before contribution.
- Every displayed score can be decomposed into retained path records with edge
  IDs and provenance references.
- The floor threshold keeps slider recompute bounded for the curated graph while
  still retaining material third-order paths.
- The bounded score is not a probability and must not be labeled as one.

## User And Judging Impact

Users can click from a score to the exact path contributions behind it. Judges
get a clear answer for cycle handling and double-counting prevention.

## Security, Data, Cost, And Performance Impact

No new data source or secret is introduced. Runtime cost is bounded by a
three-hop simple-path traversal and the floor threshold. Tests must cover
determinism, path-key uniqueness, cycle rejection, floor cutoff, and score
decomposition.

## Migration Or Rollback

This is the initial v1 decision. A later formula change requires a new ADR and a
snapshot-version bump so historical runs remain reproducible.

## Human Approval Required

No, unless a later change weakens the `RW-ALG-005` constraints.

No MUST-level requirement is weakened by this ADR.

## Affected Requirements

`RW-ALG-001`, `RW-ALG-004`, `RW-ALG-005`, `RW-ALG-006`, `RW-ALG-032`,
`RW-FR-017`, `RW-FR-018`, `RW-FR-020`, `RW-FR-021`, `RW-NFR-002`.

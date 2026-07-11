# Knowledge-graph assembly (`RIS-12`)

Assembles the curated universe + derived weights into a typed, weighted,
provenanced graph (`RW-FR-016`), keyed to a snapshot id + graph version.

## The Graft 2 write gate (`RW-ALG-032`)

**If an edge has no provenance, the edge does not exist** — enforced
structurally, not by convention:

- `ProposedEdge.record` accepts a `WeightRecord` and *only* a `WeightRecord`.
  There is no parameter that takes a raw float (`test_rejects_edge_with_raw_weight`).
- A `WeightRecord` is itself unconstructible without a validated `Provenance`
  (source doc id, quoted passage + offsets, data timestamp, method id,
  extraction confidence) — enforced in the derivations library
  (`test_rejects_edge_without_provenance`).
- The derivation method must be registered (`RW-ALG-001`), else assembly raises.

`provenance_coverage()` *measures* completeness rather than asserting it, so a
regression in the gate surfaces as < 100% in the stats report and in tests.

## Determinism & idempotency (RW-GOAL-006)

`AssembledGraph.checksum` is a SHA-256 over a canonical serialization of nodes,
edges, weights, provenance refs, and centrality. Re-assembling the same inputs
yields the same checksum (`test_assembly_is_idempotent_checksum`); any weight or
evidence change moves it. `edge_id` is derived from the edge identity plus its
evidence span, so the same disclosure always produces the same edge.

## Structural centrality, separate from impact (`RW-FR-019`)

`centrality` is **weighted PageRank** over the exposure graph (edge weight =
absolute derived weight) — a structural property answering "who is systemically
important in the exposure web", independent of any scenario. It is stored
separately from propagation impact so the UI can show both distinctly.

## Read API for the engine

`to_snapshot(pack=None)` produces an engine-ready `GraphSnapshot` (RIS-13),
optionally restricted to the `cre` or `oil` scenario pack.

## Neo4j

This module is the in-memory assembly + validation core and the source of truth
for the write gate. The Neo4j persistence layer (Cypher `MERGE` of the same
validated `AssembledGraph`) is a thin writer over this contract; it is gated
behind the same `ProposedEdge` type so no un-provenanced edge can reach the
database either.

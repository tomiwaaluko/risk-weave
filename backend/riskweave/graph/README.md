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

## Fixture-seeded graph (reduced hackathon scope)

Under the reduced RIS-12 scope the graph is not extracted live. A committed
fixture — `backend/data/fixtures/cre_graph.json`, ~15 CRE-pack entities and
typed/weighted/directed edges — carries **pre-baked** weights and provenance
(hand-authored from real filing disclosures where practical), rather than output
from the deferred Gemini pipeline (RIS-10/11).

`fixture.load_graph_fixture()` still routes every pre-baked edge through the
Graft 2 gate above: each edge weight becomes a `WeightRecord` bound to a
validated `Provenance`, then `assemble()`. A fixture edge missing any provenance
field is rejected at load (`test_missing_provenance_field_is_rejected`). So the
fixture is pre-baked, not un-provenanced.

## Neo4j store

`store.Neo4jGraphStore` writes and reads the assembled graph:

- `seed(graph)` — **drop-then-reload in one transaction**, so re-running
  reproduces the same graph (`test_reseed_reproduces_the_same_graph`). Every
  edge is written with its full provenance fields; the source `AssembledGraph`
  cannot contain an un-provenanced edge, so neither can the database.
- `read_snapshot(pack=None)` — the engine read API: adjacency + signed weights +
  provenance refs as a `GraphSnapshot`, optionally filtered to one pack.

The `neo4j` driver is imported lazily, so this package imports and unit-tests
without the driver or a database. Seed the local stack with:

```
docker compose up --wait          # brings up the Neo4j service
cd backend
uv add neo4j                      # one-time: adds the driver + updates the lock
uv run python -m riskweave.graph.seed
```

Integration tests in `test_graph_store.py` seed a live Neo4j and are skipped
when the driver or a reachable database is absent.

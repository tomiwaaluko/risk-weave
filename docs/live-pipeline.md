# Live pipeline: end-to-end graph from a real snapshot (RIS-28)

This document describes how RiskWeave assembles its **live** knowledge graph from
a real ingestion snapshot, and how to re-run assembly against a new snapshot. It
covers the gap RIS-28 closes: `/graph/seed` served a hand-authored ~15-entity
fixture; `/graph/live` now serves a graph assembled from real extraction +
resolution + derivation output over a frozen ingestion snapshot.

## Build order this wires together (spec §20, stages 3–5)

1. **Extraction (RIS-10):** Gemini strict-JSON extraction over the snapshot's
   document chunks, stored in `relationship_extractions` with full provenance
   (verbatim passage, absolute char offsets, extraction confidence).
2. **Resolution (RIS-11):** each relationship's `source_entity` / `target_entity`
   mention is resolved to a curated-universe id (`data/universe/entities.json`),
   deterministic identifiers first, Gemini only for ambiguous residuals.
3. **Derivation (RIS-9):** the disclosed magnitude phrase is turned into a number
   **by deterministic code, never the model** (`RW-AI-010`, `RW-ALG-001`) — the
   `parse_disclosed_magnitude` parser feeds `der_concentration_disclosed`, a
   registered `DER-CONCENTRATION` weight.
4. **Assembly (RIS-12):** survivors pass the same Graft 2 write gate as the
   fixture — an under-provenanced edge is unconstructible (`RW-ALG-032`).

Code: `backend/riskweave/graph/live.py` (pure builder),
`backend/riskweave/graph/build_live.py` (DB-backed CLI),
`backend/src/riskweave_api/routers/graph.py` (`POST /graph/live`).

## Snapshot binding (`RW-FR-015`)

The live graph binds to one **immutable** ingestion snapshot. The graph's
`snapshot_id` is the `DataSnapshot.name` (or `snapshot-<id>` when unnamed), and
the build is reproducible: re-running against the same frozen snapshot reproduces
the same graph checksum.

`snapshot_id 3` is the frozen Railway snapshot proven live in RIS-25 (1,009
documents, 22,384 chunks, 3,032,754 XBRL facts, 64,842 macro observations,
2026-07-12). That is the snapshot backing the live graph.

## Running assembly

From `backend/` with `.env` loaded (so `DATABASE_URL` points at the snapshot's
Postgres):

```powershell
# Assemble from the frozen Railway snapshot (id 3) and write the artifact
uv run python -m riskweave.graph.build_live --snapshot-id 3

# Or select by name
uv run python -m riskweave.graph.build_live --snapshot-name demo-2026-07-12
```

This writes `backend/data/live/graph.json` — the artifact `POST /graph/live`
serves. The command prints a stats report: node/edge/method counts, entity
coverage, resolution-layer breakdown, and per-reason drop counts.

### Re-binding to a new snapshot

1. Freeze the new ingestion snapshot (RIS-25 ingestion path).
2. Run the RIS-10 extraction pass over its chunks so `relationship_extractions`
   is populated for that `snapshot_id`.
3. Re-run `build_live --snapshot-id <new id>`.

Nothing else changes; the artifact and endpoint pick up the new graph. Override
the artifact path with `RISKWEAVE_LIVE_GRAPH_PATH` for the API, or `--out` for
the CLI.

## Serving: `/graph/live` vs `/graph/seed`

- `POST /graph/live` — the real graph assembled from the snapshot. Re-assembled
  through the Graft 2 write gate on load, registered as the runnable scenario
  `cre-live` so the propagation engine and WebSocket slider round-trip unchanged.
  Returns `503` (with the build command) if the artifact has not been built yet.
- `POST /graph/seed` — the curated CRE fixture (~15 entities), **preserved** as
  the explicit offline / demo-freeze fallback (`RW-NFR-005` spirit). Not deleted.

## Provenance on generated edges (`RW-ALG-032`)

Every edge in the live graph carries the full Graft 2 provenance set — source
document id, verbatim passage, character offsets, filing date, data timestamp,
derivation method, extraction confidence — exactly as the fixture edges do. This
is verified by automated tests: `tests/test_live_graph.py`
(`test_every_generated_edge_carries_full_provenance`) and
`tests/test_graph_live_endpoint.py` (`test_every_live_edge_has_complete_provenance`).
A relationship with no parseable disclosed magnitude yields **no edge** — no
number is fabricated (`RW-PRIN-008`).

## Entity coverage

Target: most/all of the ingested filers that resolve into the curated universe
(`data/universe/entities.json`, 125 entities, packs `cre`=78 / `oil`=52).
Resolution is deterministic-identifier-first (ticker / CIK / LEI / FRED series),
so exact-ticker and exact-CIK mentions resolve at confidence 1.0. The live build
includes only entities that anchor at least one edge — the actual coverage number
(resolved filers, resolution-layer split, drop reasons) is printed by the
`build_live` stats report for the snapshot in use.

## Derivation-method status

The relationship-extraction contract (`RelationshipExtraction`) carries a
disclosed magnitude phrase per relationship, so every live edge derives via
`DER-CONCENTRATION` (a validated disclosed fraction). The relationship's economic
category (`creditor`, `geographic_exposure`, `supplier`, …) is preserved verbatim
on the edge `relationship_type`; `method_id` records **how the number was
sourced**, not the economic category.

The numerator/denominator XBRL-derived variants — `DER-CREDIT`, `DER-GEO`,
`DER-COMMODITY` share; and the `DER-BETA` / `DER-DURATION` series methods — are
already unit-tested in RIS-9 (`backend/tests/test_methods.py`,
`test_duration.py`). They activate for the live graph as the XBRL/FRED numeric
joins are wired (each relationship mapped to the specific XBRL concepts /
return series it needs). Wiring a new method is additive: register a derivation
strategy in `live.py`; the write gate and endpoint are unchanged.

## Evaluation against real output (RIS-21 Part B)

`backend/riskweave/evaluation/live_bridge.py` adapts an assembled live graph into
the key spaces the RIS-21 metric functions consume
(`extraction_keys_from_graph`, `method_distribution`, `confidence_distribution`,
`resolution_pairs`), so the dashboard scores the **real** assembled output rather
than a fixture. The metric *values* are recomputed once the live extraction run
has populated `relationship_extractions` for the snapshot; the adapters are the
entry point the dashboard calls to consume that output.

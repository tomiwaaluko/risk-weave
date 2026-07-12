# RiskWeave Demo Script

This script is the frozen walkthrough for `RIS-22`. It binds every demo beat to
the reduced fixture bundle in `docs/demo/FROZEN_DEMO_BUNDLE.json`; it is not a
claim that the deferred live ingestion pipeline has produced a frozen snapshot.
Rehearse it from a clean `docker compose up --build --wait` environment.

## Frozen bundle

- Snapshot id: `cre-demo-2026-07-11`
- Graph version: `1.0.0`
- Engine version: `adr-001-simple-path-v1`
- Prompt version: `shock-parse-v1`
- Seed: `20260711`

## Scenario 1: CRE refinancing squeeze

### Exact NL input

`Commercial real-estate values fall 20%, refinancing rates rise 150 basis points, and stress persists 6 quarters.`

### Demo beats

1. Start in live mode and confirm the bundle badge shows `cre-demo-2026-07-11`.
2. Point out that the graph is a curated fixture with real-filing-sourced,
   pre-baked provenance; live Gemini handles parse and explanation only.
3. Select `CRE refinancing squeeze` and click `SL Green Realty Corp.`.
4. Call out direct impact, indirect impact, risk score, and structural
   centrality as separate values in the node panel.
5. Open the path from `U.S. Office Commercial Real Estate` through `SL Green
   Realty Corp.` into `Wells Fargo & Company`.
6. Click the second hop, then the third hop, to show the exact evidence panel and low-confidence badge.
7. Scroll to the passage viewer and read the highlighted quote verbatim.
8. Open the methodology section and call out source limitations before the judges ask.
9. Toggle `Replay fallback` and show that the label changes visibly while the same frozen results remain accessible.

### Follow-up question to ask

`Why isn't this just RAG?`

Answer from `docs/demo/JUDGE_QA.md`, citing the deterministic derivation and path decomposition.

## Rehearsal gate

- Run the full script three times consecutively with no code changes from a clean
  `docker compose up --build --wait`.
- Time five random number traces against `docs/demo/PROVENANCE_DRILL.md`.
- Capture a full-flow recording and store/link it in `docs/demo/RELEASE_GATE.md`.
- If any step requires ad-libbing to explain a number, the bundle is not frozen enough.

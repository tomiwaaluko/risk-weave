# RiskWeave Demo Script

This script is the frozen walkthrough for `RIS-22`. It binds every demo beat to
`docs/demo/FROZEN_DEMO_BUNDLE.json` and must be rehearsed from a clean
`docker compose up --build --wait` environment.

## Frozen bundle

- Snapshot id: `snap-demo-2026-07-11`
- Graph version: `1.1.0`
- Engine version: `adr-001-simple-path-v1`
- Prompt version: `shock-parse-v1`
- Seed: `20260711`

## Scenario 1: CRE refinancing squeeze

### Exact NL input

`Commercial real-estate values fall 20%, refinancing rates rise 150 basis points, and stress persists six quarters.`

### Demo beats

1. Start in live mode and confirm the bundle badge shows `snap-demo-2026-07-11`.
2. Point out the selected scenario card and the frozen replay label.
3. Click `Atlantic Regional Bank`.
4. Call out direct impact, indirect impact, risk score, and structural centrality as separate values.
5. Open `REIT -> title services -> CMBS loop`.
6. Click the second hop, then the third hop, to show the exact evidence panel and low-confidence badge.
7. Scroll to the passage viewer and read the highlighted quote verbatim.
8. Open the methodology section and call out source limitations before the judges ask.
9. Toggle `Replay fallback` and show that the label changes visibly while the same frozen results remain accessible.

### Follow-up question to ask

`Why isn't this just RAG?`

Answer from `docs/demo/JUDGE_QA.md`, citing the deterministic derivation and path decomposition.

## Scenario 2: Oil price shock

### Exact NL input

`Oil prices jump 25%, jet fuel costs stay elevated for two quarters, and airlines pass only part of the shock through to fares.`

### Demo beats

1. Switch the scenario selector to `Oil price shock`.
2. Keep replay mode available but start in live mode.
3. Show that the path and passage copy change while the frozen bundle metadata does not.
4. Call out the surprising path through logistics into air cargo and downstream retail sensitivity.
5. Use the methodology panel to disclose the free-tier source and any missing fare-elasticity coverage.

## Rehearsal gate

- Run the full script three times consecutively with no code changes.
- Time five random number traces against `docs/demo/PROVENANCE_DRILL.md`.
- If any step requires ad-libbing to explain a number, the bundle is not frozen enough.

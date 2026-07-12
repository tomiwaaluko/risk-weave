# RIS-22 Release Gate

This checklist closes the reduced fixture demo freeze. It records the gate for
`RW-DATA-006`, `RW-SAFE-004`, `RW-GOAL-008`, and the Section 21 completion
review without implying that the deferred live ingestion pipeline is frozen.

## Frozen artifact

- Fixture source: `backend/data/fixtures/cre_graph.json`
- Bundle manifest: `docs/demo/FROZEN_DEMO_BUNDLE.json`
- Snapshot id: `cre-demo-2026-07-11`
- Graph version: `1.0.0`
- Engine version: `adr-001-simple-path-v1`
- Prompt version: `shock-parse-v1`
- Seed: `20260711`
- Replay label: `Replay mode: precomputed results from frozen bundle`

## Acceptance gate

| Gate | Evidence to record before demo | Status |
|---|---|---|
| 3 consecutive scripted runs from clean Compose | Operator, date, command, and pass/fail notes | 1 of 3 logged (see Rehearsal log) — 2 human runs pending |
| Replay fallback switches seamlessly and is labeled | Screenshot or recording timestamp showing `Replay fallback` and replay label | Pending recording |
| Five provenance drill traces under 30 seconds each | Five rows from `docs/demo/PROVENANCE_DRILL.md` with elapsed times | Pending manual rehearsal |
| Fixture scenario reproduces identical results | `backend/tests/test_demo_freeze.py` deterministic seed test | Automated |
| Full-flow recording captured and stored | Local or hosted recording path | Pending recording |
| Section 21 completion checklist reviewed | Open gaps converted to Linear tickets | Pending review |

## Rehearsal log

### Run 1 — 2026-07-11, automated API walk (Claude Code)

Command: `docker compose down` → `docker compose up --build --wait` (cold rebuild,
including the newly committed `backend/Dockerfile` fixtures/PYTHONPATH change, PR #54).

| Step | Endpoint | Result |
|---|---|---|
| Stack health | — | 6/6 containers Healthy |
| Seed | `POST /graph/seed` | HTTP 201, 15 nodes |
| CRE parse (live Gemini) | `POST /scenarios/presets/cre/parse` | `source: gemini`, 1 attempt, no fallback; `stress_duration=6.0 quarters` parsed verbatim |
| Propagation | `POST /registry/run_scenario/cre-demo` | Ranked impacts with path decomposition (BXP 60.1, Wells Fargo 17.5) |
| Explanation (live Gemini) | `GET /scenarios/cre-demo/explanation/wfc` | `gemini-3.1-pro-preview`, no fallback, 0 guard violations, 4 citations; prose cites only computation-payload numbers |

Notes: both live Gemini call sites (parse + explanation) succeeded on the first
attempt with zero fallbacks and zero `RW-AI-011` guard violations. Still owed
before the gate closes: 2 more consecutive human-driven runs, the five timed
provenance drills, and the fallback recording.

## Known gaps to ticket after review

- Full live-ingested snapshot freeze remains deferred; do not describe the
  fixture bundle as a frozen ingestion run.
- Railway mirror remains deferred and is not on the demo-critical path.
- Any Section 21 unmet item discovered during rehearsal must be linked from
  this file before the demo branch is considered release-ready.

# Provenance Drill

Use this sheet for the `RW-GOAL-008` speed test. Every visible number in the
demo path must be traceable to source, method, and passage in under 30 seconds.

## CRE path numbers

| Visible number | Where it appears | Source document | Method | Provenance trail |
|---|---|---|---|---|
| `0.96` office exposure | Edge panel, `cre-office -> slg` | `0001040971-24-000009` | `DER-CONCENTRATION` | Graph node -> edge panel -> passage viewer |
| `0.95` NYC exposure | Edge panel, `nyc-metro -> slg` | `0001040971-24-000009` | `DER-GEO` | Graph node -> edge panel -> passage viewer |
| `0.06` SLG creditor exposure | Edge panel, `slg -> wfc` | `0000072971-24-000112` | `DER-CREDIT` | Path hop -> edge panel -> passage offsets |
| `70%` confidence badge | Edge panel, `slg -> wfc` | `0000072971-24-000112` | extraction confidence formula | Edge panel -> low-confidence badge -> methodology panel |
| `60%` confidence badge | Edge panel, `wework -> ozk` | `0001349097-24-000006` | extraction confidence formula | Edge panel -> low-confidence badge -> methodology panel |
| `15` nodes / `18` edges | Graph HUD | `backend/data/fixtures/cre_graph.json` | fixture assembly | `/graph/seed` response -> graph HUD -> fixture file |

## Drill rule

- Randomly choose five numbers before each rehearsal.
- The presenter must trace each number without searching the repo.
- If any trace exceeds 30 seconds, update the script or UI labels before the next run.

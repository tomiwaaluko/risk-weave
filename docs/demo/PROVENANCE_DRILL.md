# Provenance Drill

Use this sheet for the `RW-GOAL-008` speed test. Every visible number in the
demo path must be traceable to source, method, and passage in under 30 seconds.

## CRE path numbers

| Visible number | Where it appears | Source document | Method | Provenance trail |
|---|---|---|---|---|
| `+0.62` direct impact | Node panel, Atlantic Regional Bank | `0001456789-25-000044` | `DER-CREDIT` | Node panel -> Direct CRE loan-book hit -> edge `Atlantic Regional Bank -> Harbor Point REIT` -> passage viewer |
| `+0.19` indirect impact | Node panel, Atlantic Regional Bank | `0001888031-25-000012` and `CMBS-SERVICING-2025Q1` | `DER-CONCENTRATION`, `DER-BETA` | Node panel -> `REIT -> title services -> CMBS loop` -> hop 2 or 3 -> passage viewer |
| `55.6` risk score | Node panel | Frozen bundle path decomposition | ADR-001 score transform | Node panel -> contributing path totals -> explain `100 * (1 - exp(-abs(raw_impact)))` |
| `18%` structural centrality | Node panel | Frozen graph snapshot | transmission centrality | Node panel -> structural centrality label -> methodology panel |
| `31%` loan-book share | Edge panel weight provenance | `0001456789-25-000044` | `DER-CREDIT` | Path hop -> edge panel -> passage offsets |

## Oil path numbers

| Visible number | Where it appears | Source document | Method | Provenance trail |
|---|---|---|---|---|
| `25%` oil shock magnitude | Scenario card | Frozen bundle scenario input | scenario parser output | Scenario selector -> bundle detail |
| `+0.47` logistics transmission | Edge panel | `OIL-PACK-2025Q1` | `DER-COMMODITY` | Path hop -> edge panel -> quote |
| `61%` confidence badge | Edge panel | `AIR-CARGO-2025Q1` | extraction confidence formula | Edge panel -> low-confidence badge -> methodology panel |

## Drill rule

- Randomly choose five numbers before each rehearsal.
- The presenter must trace each number without searching the repo.
- If any trace exceeds 30 seconds, update the script or UI labels before the next run.

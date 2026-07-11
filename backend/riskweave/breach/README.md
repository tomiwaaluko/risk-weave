# Breach-distance covenant metric — Graft 1 (`RIS-16`)

The demo's signature arithmetic (spec §11): *"leverage 4.2x today, covenant
limit 4.5x, projected 4.8x under this scenario — headroom exhausted."*

## Division of labour (`RW-AI-010`)

Gemini extracts covenant **thresholds** into a strict schema with the quoted
passage stored. It never computes a ratio. Everything here is deterministic
arithmetic on XBRL facts + an extracted threshold — no model call. A
`CovenantThreshold` is unconstructible without a `Provenance`, so no covenant
number is untraceable to a filing.

## Ratios and their XBRL tags (judges may ask)

| Ratio | Formula | XBRL tags |
|---|---|---|
| Leverage | total debt / EBITDA | `LongTermDebtNoncurrent`+`LongTermDebtCurrent` (or `Liabilities`) over an EBITDA build from `NetIncomeLoss`+interest+taxes+D&A |
| Interest coverage | EBIT / interest expense | `OperatingIncomeLoss` / `InterestExpense` |
| Liquidity (current ratio) | current assets / current liabilities | `AssetsCurrent` / `LiabilitiesCurrent` |

## Projection (deterministic)

```
projected_ratio = current_ratio × (1 + sensitivity_sign × node_impact)
```

`node_impact` is the entity's signed propagated impact from the engine (RIS-13).
`sensitivity_sign` is fixed by economics, **not** extracted: leverage rises
under stress (+1), coverage and liquidity fall (−1). This is what makes the
breach distance recompute live as the severity slider moves `node_impact`.

## Breach tiers

`safe` → `thinning` (projection has eaten >75% of the pre-shock cushion) →
`exhausted` (projected value breaches the threshold).

## Status

Deterministic core + math is complete and hand-verified (the §11 regional-bank
beat is `test_regional_bank_leverage_beat`). Populating real thresholds for
10–20 entities needs the RIS-10 covenant-extraction schema and RIS-8 XBRL
ingestion; per `RW-PRIN-008` no thresholds are fabricated here — the library is
data-ready and the registry/slider wiring plugs into RIS-14 once those land.

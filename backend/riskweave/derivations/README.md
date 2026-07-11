# Deterministic weight-derivation library (`RIS-9`)

The defensibility core of RiskWeave (spec **§12**, `RW-ALG-001..004`, `RW-ALG-007`).
Every edge weight entering propagation is produced here by a **registered
deterministic method** — never estimated by Gemini (`RW-AI-010`). Gemini finds
the sentence; this code turns it into the number.

Every derivation returns a [`WeightRecord`](provenance.py) that **cannot be
constructed without complete provenance** — a source document id, the exact
quoted passage with character offsets, a data timestamp, the method id/version,
and an extraction confidence. That is the "no edge without provenance" invariant
enforced in the type system, not by convention.

## Method id → spec §12.1 row

| Method id | §12.1 edge / exposure type | Deterministic derivation | Source data | Primary / fallback callable |
|---|---|---|---|---|
| `DER-COMMODITY` | Commodity dependency (e.g. jet fuel) | Cost-line share of operating expenses from XBRL; else OLS factor beta vs the commodity series | XBRL, FRED/commodity history, market returns | `der_commodity_cost_share` / `der_commodity_factor_beta` |
| `DER-CONCENTRATION` | Supplier / customer dependency | Disclosed revenue-concentration % (validated verbatim per `RW-ALG-002`); else segment revenue share | 10-K concentration disclosures, XBRL segments | `der_concentration_disclosed` / `der_concentration_segment_share` |
| `DER-CREDIT` | Creditor / lending exposure | Exposure over total loan portfolio, from loan-portfolio composition disclosures | Bank 10-K/10-Q disclosures | `der_credit_portfolio_share` |
| `DER-DURATION` | Interest-rate sensitivity (debt / security nodes) | Modified duration, closed-form (**Graft 3**) | Bond terms from filings, current yield inputs | `der_duration` — **stub only**, implemented in `RIS-17` |
| `DER-GEO` | Geographic exposure | Revenue-by-geography over total revenue | XBRL segment reporting | `der_geo_revenue_share` |
| `DER-BETA` | Equity market sensitivity | OLS beta of the asset on the market from historical returns | Market history | `der_beta` |

The registry ([`registry.py`](registry.py)) is the single source of truth for
`method_id → version → spec row`; `WeightRecord.method_version` is stamped from
it. Look methods up with `get_method(id)` / `list_methods()`.

## Design invariants

- **Pure functions.** Every `DER-*` function takes already-fetched numbers
  (XBRL line items, disclosure fractions, or return series) plus the
  `Provenance` they came from. No database, no network, no clock. Wiring real
  XBRL/FRED/price data in is ingestion's job (`RIS-8`), so this library is
  independent of that data contract.
- **No model-produced numbers.** Nothing here calls an LLM. Shares are
  arithmetic; betas are closed-form OLS (`statsmodels`) on caller inputs.
- **Reject, don't guess** (`RW-PRIN-008`). The `disclosed_magnitude` parser
  ([`magnitude.py`](magnitude.py)) refuses qualitative phrases, ambiguous
  multi-percentage strings, and out-of-domain values rather than inventing a
  number. Shares that would exceed 1, zero denominators, thin/degenerate
  regressions all raise `DerivationError`.
- **Deterministic.** Identical inputs give identical outputs. OLS is
  closed-form, so betas are reproducible with no seed (`test_beta_deterministic`).

## `disclosed_magnitude` parser

`parse_disclosed_magnitude("approximately 28% of operating expenses") → 0.28`,
flagging `is_approximate`. Handles ranges (midpoint + `range_low/high`),
footnote markers (`28%(1)`, `28%¹`, `28%*`), and one-sided bounds
(`at least 20%` → `bound="lower"`). See `tests/test_magnitude.py` for the
adversarial set.

## `DER-BETA` equity-price source (`RW-DATA-002`)

This library does **not** fetch prices — it consumes pre-fetched daily return
series — but the source is fixed here for the honesty view:

- **Chosen source: Tiingo end-of-day (free tier).** Documented terms of service
  and rate limits (~1,000 requests/day, ~500 unique symbols/month on the free
  tier), which comfortably covers the 100–200-entity demo universe.
- **Rejected: unofficial CSV scrapers (e.g. Stooq).** No documented rate limit
  or terms; unsuitable for a defensible, reproducible pipeline.
- **Known limitations to disclose in the demo:** end-of-day granularity only
  (no intraday); free-tier symbol/day caps; corporate-action adjustment quality
  varies. Betas are historical OLS estimates, and per `RW-ALG-007` the displayed
  confidence is a data-quality signal, **not** a statistical guarantee.

The actual fetch, caching, rate-limiting, and snapshot binding live in the
ingestion pipeline (`RIS-8`).

## Running the tests

```
cd backend
python -m venv ../.venv && ../.venv/bin/python -m pip install -e '.[dev]'
../.venv/bin/python -m pytest
```

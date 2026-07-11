# ADR-007: Macro-Series Catalog

## Status

Accepted for v1.

## Context

RiskWeave v1 has two scenario packs: commercial real estate decline and oil
price shock. The spec names FRED or ALFRED as approved sources and leaves the
exact macro-series catalog open. The catalog must be small, reproducible, and
directly useful for deterministic derivations and scenario context.

## Original Requirement

Choose the exact macro-series catalog for the CRE and oil packs using approved
free sources.

## Proposed Change

Adopt a small FRED/ALFRED catalog covering CRE exposure, CRE delinquency, oil
benchmarks, rates, unemployment, and inflation controls.

## Reason

The catalog is broad enough for the two v1 scenario packs but small enough to
ingest, snapshot, cite, and explain reliably.

## Decision

Use this initial FRED/ALFRED series catalog.

Commercial real estate pack:

| Purpose | Series ID | Series |
|---|---:|---|
| CRE bank exposure level | `CREACBM027NBOG` | Real Estate Loans: Commercial Real Estate Loans, All Commercial Banks |
| CRE delinquency stress | `DRCRELEXFACBS` | Delinquency Rate on Commercial Real Estate Loans, Excluding Farmland, Booked in Domestic Offices, All Commercial Banks |
| Policy-rate context | `DFF` | Federal Funds Effective Rate |
| Long-rate / duration context | `DGS10` | Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity |
| Macro control | `UNRATE` | Unemployment Rate |
| Inflation control | `CPIAUCSL` | Consumer Price Index for All Urban Consumers: All Items in U.S. City Average |

Oil shock pack:

| Purpose | Series ID | Series |
|---|---:|---|
| Primary U.S. oil shock input | `DCOILWTICO` | Crude Oil Prices: West Texas Intermediate (WTI) - Cushing, Oklahoma |
| Global oil benchmark | `DCOILBRENTEU` | Crude Oil Prices: Brent - Europe |
| Policy-rate context | `DFF` | Federal Funds Effective Rate |
| Long-rate / duration context | `DGS10` | Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity |
| Macro control | `UNRATE` | Unemployment Rate |
| Inflation control | `CPIAUCSL` | Consumer Price Index for All Urban Consumers: All Items in U.S. City Average |

Use ALFRED vintages when a demo snapshot needs vintage reproducibility; otherwise
store the FRED observation timestamp, retrieval timestamp, units, frequency, and
source release metadata in the data snapshot.

## Alternatives Considered

- Large macro catalog: rejected because v1 needs demo reliability and clear
  provenance more than breadth.
- Licensed CRE vacancy or property-price feeds: rejected for v1 because the spec
  restricts sources to free/provider-compliant inputs.
- Oil futures curves: rejected for v1 because the oil pack only needs a clear
  shock input and deterministic exposure propagation.

## Consequences

The first ingestion ticket can implement a small known series list and tests can
assert units/frequency metadata. Missing domain-specific series should become
new tickets, not silent additions.

## User And Judging Impact

Users see scenario inputs backed by recognizable public series. Judges can verify
the series IDs and source metadata quickly during Q&A.

## Security, Data, Cost, And Performance Impact

FRED/ALFRED are approved free sources. Ingestion must respect provider terms and
rate limits. Data is small and suitable for local Docker Compose snapshots.

## Migration Or Rollback

Adding or replacing series requires an ADR amendment or a new ADR. Existing run
snapshots keep the series IDs and observation vintages they used.

## Human Approval Required

No for the initial catalog. Yes for licensed data sources or non-free providers.

No MUST-level requirement is weakened by this ADR.

## Affected Requirements

`RW-DATA-001`, `RW-DATA-005`, `RW-ALG-001`, `RW-ALG-004`, `RW-ALG-031`,
`RW-ALG-032`, `RW-SCOPE-001`, `RW-SCOPE-002`, `RW-SCOPE-003`, `RW-NFR-003`.

## Sources

- FRED `CREACBM027NBOG`: https://fred.stlouisfed.org/series/CREACBM027NBOG
- FRED `DRCRELEXFACBS`: https://fred.stlouisfed.org/series/DRCRELEXFACBS
- FRED `DCOILWTICO`: https://fred.stlouisfed.org/series/DCOILWTICO
- FRED `DCOILBRENTEU`: https://fred.stlouisfed.org/series/DCOILBRENTEU
- FRED `DFF`: https://fred.stlouisfed.org/series/DFF
- FRED `DGS10`: https://fred.stlouisfed.org/series/DGS10
- FRED `UNRATE`: https://fred.stlouisfed.org/series/UNRATE
- FRED `CPIAUCSL`: https://fred.stlouisfed.org/series/CPIAUCSL

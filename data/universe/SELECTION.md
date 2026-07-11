# RiskWeave V1 Entity Universe Selection

## Purpose

This universe supports the v1 commercial real estate and oil shock demo packs
for `RIS-7`. It is curated for depth, traceability, and demo reliability, not
market coverage.

This file implements `RW-SCOPE-001`, `RW-SCOPE-002`, `RW-FR-010`, and
`RW-DATA-001`.

## Selection Principles

- Keep the universe between 100 and 200 entities so the graph remains inspectable
  and slider recompute stays plausible for v1.
- Prefer SEC-reporting public companies with resolvable ticker and CIK values so
  downstream EDGAR and XBRL ingestion can bind filings deterministically.
- Include enough commercial-real-estate depth for judges to inspect banks,
  REITs, property services, housing, title insurance, and construction-linked
  proxies.
- Include enough oil-pack depth for producers, refiners, midstream firms,
  services firms, airlines, parcel carriers, trucking, rail, and logistics.
- Include macro, commodity, geography, and sector nodes that make graph paths
  legible without expanding into a broad-market universe.

## Scope Guard

Selection does not imply wrongdoing, endorsement, investment merit, credit
quality, or a buy/sell/hold view for any entity. Entities are included only
because their public filings, business model, sector role, or macro sensitivity
make them useful for demonstrating deterministic contagion paths.

## Composition

The universe file currently contains 125 entities (as generated on 2026-07-11):

- 25 banks or financial institutions for CRE credit and breach-distance paths.
- 25 REITs or property-related infrastructure companies.
- 20 additional CRE-connected service, housing, title, building, or equipment
  proxies.
- 23 energy, refining, oilfield-services, or midstream companies.
- 20 airline, parcel, trucking, rail, and logistics companies.
- 12 non-SEC nodes for FRED/ALFRED macro series, commodities, sectors, and U.S.
  geography.

## Breach-Distance Candidates

The initial breach-distance candidate set contains 16 banks or financial
institutions:

`JPM`, `BAC`, `C`, `WFC`, `USB`, `PNC`, `TFC`, `COF`, `KEY`, `RF`, `HBAN`,
`FITB`, `MTB`, `ZION`, `CFG`, `ALLY`.

These are candidates for `RW-ALG-030` because public bank filings are expected
to contain lending, capital, liquidity, or covenant-adjacent disclosures useful
for the v1 breach-distance metric. The candidate flag is not a claim that an
entity is distressed.

## Verification

All SEC-reporting entities in `entities.json` were generated from ticker symbols
resolved against the official SEC `company_tickers.json` file on 2026-07-11:

https://www.sec.gov/files/company_tickers.json

Non-SEC nodes intentionally have no CIK or ticker. Their source identifiers are
FRED series IDs from ADR-007 or curated sector/geography metadata.

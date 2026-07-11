---
title: RIS-8 batch ingestion requirements
date: 2026-07-11
ticket: RIS-8
artifact_contract: ce-requirements/v1
---

# RIS-8 batch ingestion requirements

## Outcome

Provide a repeatable pre-demo batch that loads the curated entity universe's SEC filings,
SEC company facts, and the ADR-007 FRED catalog into PostgreSQL and freezes the visible
records behind an immutable, reproducible snapshot identifier.

## Requirements

- Persist ingestion runs, filing documents, canonical text chunks with absolute character
  offsets, XBRL facts, macro series/observations, snapshots, and snapshot membership.
- Retain source identifiers, retrieval timestamps, filing/as-of dates, and provider payload
  metadata required by `RW-DATA-003`.
- Fetch 10-K, 10-Q, and 8-K filings plus company facts for each unique CIK in
  `data/universe/entities.json` using an identifying User-Agent and a shared SEC limiter that
  never exceeds ten requests per second.
- Fetch the eight series fixed by ADR-007 with a server-side `FRED_API_KEY`; handle missing
  observations without inventing values.
- Make provider writes idempotent by stable natural keys and content hashes. A second run
  over identical inputs changes no provider records.
- Canonicalize and chunk filing text according to ADR-003 so every chunk slice exactly
  reconstructs its portion of the stored canonical document.
- Create snapshots from a sorted manifest of visible record identities and content hashes.
  Existing snapshot membership and manifests are immutable.
- Expose one CLI entrypoint that applies migrations, runs the complete batch, and names the
  resulting snapshot. Provider calls remain injectable for deterministic tests.

## Success criteria

- A fixture-backed clean-database run completes and the second run is a provider-data no-op.
- Tests prove exact chunk offset reconstruction, the ten-request-per-second cap with a fake
  clock, and immutable snapshot behavior (`test_snapshot_is_immutable`).
- PostgreSQL migrations upgrade from an empty database and all existing backend tests remain
  green.
- No credential is committed; the FRED key is read from environment configuration.

## Scope boundaries

- No Gemini extraction, entity resolution, weight derivation, equity prices, graph assembly,
  live-demo scraping, or ALFRED vintage ingestion.
- No provider-specific values enter propagation and no new macro series extend ADR-007.

## Traceability

`RW-FR-011..015`, `RW-DATA-001..005`, `RW-NFR-001`, ADR-003, and ADR-007.

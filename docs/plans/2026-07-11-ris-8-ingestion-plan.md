---
title: RIS-8 batch ingestion implementation plan
date: 2026-07-11
ticket: RIS-8
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
requirements: docs/brainstorms/2026-07-11-ris-8-ingestion-requirements.md
product_contract_source: ce-brainstorm
---

# RIS-8 batch ingestion implementation plan

## Goal capsule

Build the PostgreSQL-backed, provider-compliant batch ingestion spine required by
`RW-FR-011..015` and `RW-DATA-001..005`, with immutable snapshots and deterministic tests.

## Scope boundaries

Implement only ingestion, persistence, snapshotting, and the batch CLI. Preserve the
`Scope boundaries` in `docs/brainstorms/2026-07-11-ris-8-ingestion-requirements.md`.

## Implementation units

### U1 — Persistence and migrations

- **Goal:** Add SQLAlchemy models and Alembic migrations for all RIS-8 tables, UTC retrieval
  timestamps, JSON provider metadata, source URLs, normalization metadata, and DB-triggered
  immutable snapshot membership. XBRL identity includes CIK, taxonomy, concept, unit,
  period/start, accession, form, fiscal period/year, and frame where present.
- **Files:** `backend/alembic*`, `backend/src/riskweave_api/ingestion/models.py`, database
  helpers, settings, dependencies, lockfile.
- **Execution note:** Test schema constraints and repository idempotency first with SQLite;
  verify the migration against PostgreSQL in the end-to-end gate.
- **Test scenarios:** identical natural-key/content-hash duplicates are a no-op; conflicting
  hashes are rejected; snapshot membership cannot be inserted, changed, or deleted after
  freeze, including direct PostgreSQL mutation.

### U2 — Provider clients and rate limiting

- **Goal:** Implement injectable SEC submissions/companyfacts/archive clients and FRED
  series-metadata/observations clients. Use fixed HTTPS hosts, no redirects, identifying
  headers, bounded timeouts/body sizes/record counts, schema/content-type checks, and
  redacted provider errors. A DB advisory lock prevents concurrent batch runs.
- **Files:** `backend/src/riskweave_api/ingestion/clients.py`, `rate_limit.py`, catalog module.
- **Execution note:** Begin with fake-transport and fake-clock failures.
- **Test scenarios:** ten evenly admitted SEC requests per second; concurrent runs fail fast;
  required User-Agent and FRED key; correct endpoint/parameters; malformed/oversized payloads
  fail closed; errors and CLI output never expose the key; missing FRED values are skipped.

### U3 — Canonical filing documents and chunks

- **Goal:** Extract readable canonical text from filing HTML and chunk it with ADR-003 sizes,
  overlap, and absolute offsets.
- **Files:** `backend/src/riskweave_api/ingestion/canonicalize.py`, `chunking.py`, and tests.
- **Execution note:** Test offset reconstruction before parsing implementation.
- **Test scenarios:** each chunk equals `document[start:end]`; long sections respect the hard
  maximum; repeated runs produce identical content hashes and boundaries.

### U4 — Orchestration, snapshots, and CLI

- **Goal:** Load unique CIKs and the most recent three filings per configured form (including
  older SEC submissions index files when necessary), plus ADR-007 series metadata and
  observations. Persist transactionally, compute a sorted manifest hash, freeze membership,
  and expose `riskweave-ingest`, which applies migrations before ingestion.
- **Files:** service/repository/CLI modules, `pyproject.toml`, settings, integration tests.
- **Execution note:** Drive with fixture providers through a clean-DB double-run test.
- **Test scenarios:** full fixture run; second run provider-data no-op; same visible data maps
  to the same snapshot; same name with different manifest is rejected; CLI applies migrations
  first and reports counts without credentials.

## Verification contract

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest`
- `uv run alembic upgrade head` against the Compose PostgreSQL service
- fixture-backed CLI twice against a clean PostgreSQL database, comparing counts/snapshot ID
- tracked-file credential scan and inspection that the API key is environment-only

## Definition of done

All acceptance criteria on RIS-8 pass; migrations work from empty PostgreSQL; provider terms
are documented in code/tests; full verification is green; PR cites RIS-8 and requirement IDs.

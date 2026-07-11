---
title: Build immutable snapshots from provider identities
date: 2026-07-11
category: architecture-patterns
module: batch ingestion
problem_type: architecture_pattern
component: database
severity: high
applies_when:
  - Persisting reproducible snapshots of externally sourced records
  - Enforcing audit invariants below an application repository layer
tags:
  - immutable-snapshots
  - natural-keys
  - provenance
  - postgresql
---

# Build immutable snapshots from provider identities

## Context

An ingestion snapshot must reproduce the same logical dataset across clean databases and
reruns. Database-generated row IDs cannot provide that guarantee: insertion order, stale rows,
or a rebuilt database can change them without changing the provider data. Application-only
freeze checks are also insufficient because direct SQL or a future code path can bypass them.

## Guidance

Build the manifest only from records visible to the current ingestion run. Identify each member
with its provider-natural identity and content hash—for example an SEC accession number, an XBRL
identity hash, or `FRED series_id + observation_date`. Sort these tuples before hashing the
manifest. The RIS-8 repository implements that deterministic manifest construction in
`backend/src/riskweave_api/ingestion/repository.py`.

Enforce the freeze twice:

1. Repository methods reject membership changes after `frozen_at` is set.
2. PostgreSQL triggers reject direct inserts, updates, reassignment, and deletes involving a
   frozen snapshot. The migration-local trigger definitions live in
   `backend/alembic/versions/20260711_01_ingestion_schema.py`.

Insert and flush all membership rows before setting `frozen_at`. Freezing first can cause the
database trigger to reject the snapshot's own pending member inserts when SQLAlchemy flushes.

## Why This Matters

Stable provider identities make a snapshot independent of local surrogate keys and unrelated
database history. Database triggers make immutability a storage invariant rather than a promise
made by one caller. Together they support `RW-FR-015`: a scenario run can bind to a logical
dataset that cannot silently drift.

## When to Apply

- External provider records are ingested idempotently and later referenced by scenario runs.
- Reproducibility must survive database rebuilds or different insertion orders.
- Snapshot membership must remain immutable even under direct database access.

## Examples

Prefer manifest members shaped like:

```text
("document", accession_number, content_hash)
("xbrl_fact", identity_hash, content_hash)
("macro_observation", "series_id:observation_date", content_hash)
```

Avoid `(record_type, database_row_id, content_hash)` unless the row ID is itself a stable,
provider-owned identifier.

## Related

- `docs/adr/ADR-003-filing-chunking-offsets.md`
- `docs/adr/ADR-007-macro-series-catalog.md`

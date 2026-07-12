# ADR-009: Incremental-Commit Batch Ingestion

## Status

Accepted for v1.

## Context

The first live batch ingestion (`RIS-25`, `RW-FR-011..015`) was executed as a
one-off Railway job against the Hobby-tier 8 GB container. `IngestionService.run`
originally performed the entire curated-universe ingest — every SEC filing's
canonical text, every derived chunk, and every XBRL fact for all 113 CIKs — inside
a single database transaction, committing only once at the end. Held ORM instances
accumulated in the SQLAlchemy identity map for the full run.

On 2026-07-12 the job ran ~23 minutes, grew to ~1.1 GB during the SEC-filing pass,
then spiked to the 8 GB limit during the XBRL company-facts pass and was
OOM-killed (`Killed`, no snapshot produced). Memory grew monotonically because
nothing was ever released.

## Original Requirement

`RW-FR-014` — re-running ingestion produces no duplicates (idempotent).
`RW-FR-015` — an immutable logical snapshot ID freezes the ingested set that
scenario runs bind to. Neither requirement prescribes a single-transaction
implementation.

## Proposed Change

Commit and `expunge_all()` after each provider unit (per CIK for SEC + XBRL, per
series for FRED) so ORM instances do not accumulate. The in-memory `members`
list retains only small `(record_type, record_id, content_hash)` identity tuples,
which are cheap. The immutable snapshot is still created **once at the end** from
the full `members` set and frozen atomically in the final commit.

Remove the cross-run database lock entirely. The original transaction-scoped
advisory lock (`pg_try_advisory_xact_lock`) was released by the initial
`IngestionRun` commit, leaving the bulk of the run unguarded. A session-level
advisory lock (`pg_try_advisory_lock`) was then tried so it would survive the
per-batch commits, but with the connection pool it was acquired on one connection
while the `finally` unlock ran on another, so it leaked and **wedged every
subsequent run** (`RuntimeError: another ingestion run is active`). Concurrency is
instead prevented by the single-replica, deploy-triggered one-off job model, and
correctness under any overlap is guaranteed by the idempotent content-hash /
accession upserts that already satisfy `RW-FR-014`.

## Reason

Bounded, near-constant memory (observed well under 2 GB) lets the full run complete
inside the 8 GB Hobby container with no plan upgrade or memory-limit increase — the
most cost-efficient fix — and keeps ingestion robust as the universe grows.

## Decision

Adopt incremental per-unit commits with identity-map expunging, and no
database-level cross-run lock (idempotent upserts plus single-replica execution
provide the guarantees the lock was meant to).

## Alternatives Considered

- **Raise the container memory limit / upgrade plan:** rejected as the primary fix
  — it masks unbounded growth, adds recurring cost on the $5 Hobby plan, and still
  fails once the universe outgrows the new ceiling.
- **Batch commits within a single CIK's XBRL loop:** deferred — per-unit commits
  already bound peak memory to one filer's footprint; finer batching can be added
  if a single filer's company-facts ever dominates.
- **Keep the single transaction, stream instead of buffer:** rejected — a larger
  rewrite than the observed problem warrants.

## Consequences

A mid-run crash now leaves already-committed provider rows in place instead of
rolling the whole run back. This is acceptable and arguably better: no snapshot is
created on failure (so no scenario binds to a partial set), the run is marked
`failed`, and a re-run resumes idempotently (`RW-FR-014`) via the existing
content-hash / accession-number checks, then creates the snapshot. Snapshot
immutability (`RW-FR-015`) is unchanged: the snapshot is built and frozen in one
final step over the complete member set.

## User And Judging Impact

None visible in the product. The live snapshot scenario runs bind to is produced
exactly as before; only the ingestion job's internal transaction boundaries change.

## Security, Data, Cost, And Performance Impact

No new data sources or secrets. Lowers peak memory (and therefore billable memory)
for the batch job. Slightly more commits, negligible against SEC rate limiting
(10 req/s dominates wall-clock time).

## Migration Or Rollback

Pure code change in `IngestionService.run`; no schema migration. Rolling back
reintroduces the OOM on the 8 GB container. Snapshots already produced are
unaffected.

## Human Approval Required

No new provider or non-free source. This ADR records a transaction-boundary
implementation change that preserves the observable `RW-FR-014`/`RW-FR-015`
contract; no MUST-level requirement is weakened.

## Affected Requirements

`RW-FR-011`, `RW-FR-012`, `RW-FR-013`, `RW-FR-014`, `RW-FR-015`, `RW-NFR-001`,
`RW-DATA-003`, `RW-DATA-004`.

# ADR-008: Railway as Primary Always-On Host (Dockerfile-Built)

## Status

Accepted for v1 (approved 2026-07-11; recorded 2026-07-12).

## Context

Spec §14 settled Docker Compose as the packaging format and §25.3 treated a
cloud host as an optional mirror of the local stack. Post-hackathon, RiskWeave
needs a **primary, always-on** home for the backend and its three data stores
(PostgreSQL, Neo4j, Redis) so scenario runs, the WebSocket slider, and batch
ingestion can operate against hosted infrastructure rather than an ephemeral
local stack. This ADR promotes a cloud host from "optional mirror" to primary,
without changing the packaging format.

## Original Requirement

Spec §14 / `RW-NFR-005`: packaging is Docker Compose. Spec §25.3: cloud host is
an optional mirror. Reproducibility (`RW-NFR-001`) requires that what runs in
production is the same artifact CI tested.

## Proposed Change

Adopt **Railway** as the primary always-on host. Railway deploys the **same
Docker images built from the committed Dockerfiles** (`backend/Dockerfile`),
built from the same source the local `docker-compose.yml` and CI `containers`
job build — **not** a Nixpacks rebuild. Local Docker Compose remains fully
supported for development, CI, and as the offline demo fallback.

## Reason

Financial correctness and reproducibility (§0.4 priority order) require that the
hosted artifact is byte-for-byte the artifact CI validated. A Nixpacks build
would produce a *different* image than `backend/Dockerfile`, reintroducing the
production drift the Docker packaging decision was meant to eliminate. Pinning
Railway to build the committed Dockerfiles keeps one artifact across dev, CI,
and prod. Railway is chosen over alternatives for first-class managed Postgres
and Redis plus support for a Docker-image Neo4j service with a volume, all on a
free/hobby tier suitable for a demo-scale deployment.

## Decision

- Railway is the primary always-on host for the backend and the three data
  stores.
- Railway builds services from their committed Dockerfiles (root dir +
  `dockerfilePath` pinned in a committed `railway.json`), never Nixpacks.
- Docker Compose stays the packaging format of record and the offline fallback;
  the CI `containers` job is preserved.
- Secrets are supplied exclusively through Railway environment variables
  (`RW-SEC-001`, `RW-SEC-004`); none enter the repo.

## Alternatives Considered

- **Nixpacks build on Railway:** rejected — produces a different artifact than
  CI tested, reintroducing prod drift and violating the reproducibility
  priority.
- **Supabase (Postgres) + Vercel (backend):** rejected as the primary data host
  because neither hosts Neo4j, which the propagation graph depends on; would
  split state across providers and still require a separate Neo4j service. (Vercel
  remains the intended *frontend* host — see RIS-26.)
- **Kubernetes / self-managed cluster:** rejected — Kubernetes and Kafka are
  prohibited for v1 (spec §5.3, CLAUDE.md invariants).

## Consequences

RIS-25 stands up the Railway project, applies Alembic migrations, and runs the
first live batch ingestion into hosted Postgres. Deploys become reproducible and
one-click from GitHub. Deleting the Dockerfiles or `docker-compose.yml`, or
removing the CI `containers` job, is explicitly out of scope and would violate
this ADR.

## User And Judging Impact

A live, always-on URL means the system can be demonstrated without a local
stack. Judges and users hit real hosted infrastructure running the same
containers CI verified.

## Security, Data, Cost, And Performance Impact

Secrets live only in Railway variables, never in the repo or client. Free/hobby
tier is sufficient for demo-scale data; cost notes live in the setup guide. SEC
fair-use requires an identifying `SEC_USER_AGENT`; the multi-hour EDGAR ingestion
run is rate-limit bound (10 req/s) and runs unattended.

## Migration Or Rollback

Rollback is switching the hosted deploy off and running locally via Docker
Compose, which stays fully supported. Changing the host or the build method
(e.g. to Nixpacks) requires a new ADR amending this one.

## Human Approval Required

Yes — provisioning the Railway project, setting production secrets, and starting
the first live ingestion run are human-operated steps (no Railway MCP is
available in the agent environment).

No MUST-level requirement is weakened by this ADR. Docker Compose packaging
(`RW-NFR-005`) is preserved; Railway hosts those same containers.

## Affected Requirements

`RW-NFR-001`, `RW-NFR-003`, `RW-NFR-004`, `RW-NFR-005`, `RW-SEC-001`,
`RW-SEC-004`, `RW-FR-011`..`RW-FR-015`. Supersedes spec §25.3 re: mirror →
primary.

## Sources

- Railway Dockerfile builds: https://docs.railway.com/guides/dockerfiles
- Railway config-as-code (`railway.json`): https://docs.railway.com/reference/config-as-code

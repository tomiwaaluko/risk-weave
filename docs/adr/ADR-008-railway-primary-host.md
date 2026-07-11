# ADR-008: Railway as Primary Host (Deploy the Compose Containers, Do Not Replace Them)

## Status

Accepted for v1.

## Context

Spec §25.3 settled the hosting posture as `demo_primary: local_docker_compose`
with Railway as an optional cloud mirror that "MUST NOT be the demo-critical
path." That posture assumed the deliverable was a locally-run demo.

The project is now also being deployed as a live, always-on service that users
reach directly. This raises Railway from a convenience mirror to a primary host.
Because §25.3 and `RW-NFR-005` are settled, promoting Railway requires this ADR
(spec §0.3).

A separate, related proposal — deleting the Dockerfiles and `docker-compose.yml`
and rebuilding on Railway via Nixpacks — was rejected and is explicitly out of
scope here (see Alternatives Considered).

## Original Requirement

- `RW-NFR-005`: "Packaging is Docker Compose."
- §25.3: local Docker Compose is the primary demo target; Railway is an optional
  mirror of the same containers and must not be demo-critical.

## Proposed Change

Promote Railway from "optional mirror" to the **primary deployment host** for the
backend (and, with ADR-scoped alignment, the frontend), while keeping Docker
Compose as the packaging format and the local development/CI path.

## Reason

Deploying to Railway and keeping Docker are not in conflict: Railway builds and
runs Docker images directly. The value of Docker is that the image tested locally
and in CI is byte-for-byte the image that ships. Building on Railway from the
existing `backend/Dockerfile` preserves that test-to-production guarantee, which
is *more* important once the deployment is live, not less. Local Compose is
retained so the demo can run offline with no cloud dependency (protecting the
`RW-NFR-002` ≤500 ms slider budget on the venue path).

## Decision

1. Railway is the primary always-on host for the backend, built from
   `backend/Dockerfile` (not Nixpacks). Postgres, Redis, and Neo4j run as Railway
   services per RIS-25.
2. The Next.js frontend is deployed to Vercel as its production host, with
   PR previews retained for review velocity (RIS-26).
3. Local `docker compose up` remains fully supported for development and CI, and
   the CI `containers` job is retained as the reproducibility guard.
4. Secrets live only in platform env vars (`RW-SEC-001`, `RW-SEC-004`); the
   Gemini API key is server-side only and never in the client bundle or repo.
5. No Dockerfile or `docker-compose.yml` is deleted. `RW-NFR-005` (Docker Compose
   packaging) is preserved — Railway deploys those same containers.

## Alternatives Considered

- **Delete Docker, build on Railway with Nixpacks (the original prompt).**
  Rejected: Nixpacks would build a different artifact than the one tested locally
  and in CI, reintroducing test-to-production drift precisely when the project is
  going live. It also removes the offline local demo path and weakens
  `RW-NFR-005` with no offsetting benefit.
- **Keep Railway as an optional mirror only (unchanged §25.3).** Rejected: does
  not reflect that the project now needs a real, reachable deployment.

## Consequences

§25.3's `cloud_mirror_optional: railway` is superseded by "railway: primary host,
built from the Compose containers." The local Compose demo remains a supported and
recommended fallback for the judged/live-venue path. Team must keep the Railway
image build pinned to the Dockerfiles so prod and local stay identical.

## User And Judging Impact

Users get a live, shareable deployment. Judges can still run or inspect the exact
same containers locally, and the ≤500 ms slider budget stays guaranteeable on the
local path if network conditions at the venue are poor.

## Security, Data, Cost, And Performance Impact

Secrets remain in platform env vars only. Stay on Railway/Vercel free/hobby tiers.
The deployment carries only deterministic run payloads over WSS (per ADR-005); no
Gemini key reaches the client.

## Migration Or Rollback

If Railway hosting proves unsuitable, the local Docker Compose stack is unchanged
and remains a complete, self-contained fallback — no rollback work required beyond
pointing traffic back at the local/demo stack.

## Human Approval Required

Yes — this promotes a settled hosting posture (§25.3) and was approved by the
project owner (Tomiwa) on 2026-07-11.

No MUST-level requirement is weakened: `RW-NFR-005` (Docker Compose packaging) is
preserved; only the §25.3 mirror-vs-primary designation changes.

## Affected Requirements

`RW-NFR-005`, `RW-NFR-002`, `RW-NFR-003`, `RW-NFR-004`, `RW-SEC-001`,
`RW-SEC-004`; spec §25.3.

## Sources

- Railway Dockerfile builds: https://docs.railway.com/guides/dockerfiles
- Spec §25.3 (hosting posture) and `RW-NFR-005` (packaging).

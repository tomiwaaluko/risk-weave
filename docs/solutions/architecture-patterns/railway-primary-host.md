# Railway as the primary always-on host

Governing decision: [ADR-008](../../adr/ADR-008-railway-primary-host.md). Railway
hosts the **same Docker images built from the committed Dockerfiles** — never a
Nixpacks rebuild. Local Docker Compose stays the packaging format of record and
the offline fallback.

No Railway MCP is available in the agent environment, so the provisioning steps
below are human-operated (Railway dashboard or the `railway` CLI). The
repo-side artifacts (`railway.json`, `.env.example` alternates, this doc) are
already committed.

## Services

| Service | How it runs on Railway | Notes |
|---|---|---|
| `backend` | Built from `backend/Dockerfile` via `railway.json` | Root directory MUST be the repo root (the Dockerfile COPYs `backend/src`, `backend/riskweave`, `data/universe` from repo-root context, matching `docker-compose.yml`'s `context: .`). |
| `postgres` | Railway PostgreSQL plugin | Managed image, no build. |
| `redis` | Railway Redis plugin | Managed image, no build. |
| `neo4j` | Docker image service (`neo4j:2026.05.0`) + volume on `/data` | Public image, not built from this repo. Set `NEO4J_AUTH=neo4j/<password>`. |

Frontend hosting is **out of scope** here — it goes to Vercel (RIS-26).

## One-time provisioning

1. Create a Railway project named `riskweave`.
2. Add the **PostgreSQL** and **Redis** plugins.
3. Add a **Neo4j** service from the `neo4j:2026.05.0` Docker image; attach a
   volume mounted at `/data`; set `NEO4J_AUTH=neo4j/<password>`; expose ports
   7474 (browser) and 7687 (bolt).
4. Add the **backend** service from this GitHub repo. In its settings, set the
   **root directory to `/`** (repo root) and confirm it picks up `railway.json`
   (Dockerfile build, `backend/Dockerfile`). Do NOT let it fall back to Nixpacks.
5. Set the backend service variables (values from the plugin reference variables;
   never commit real values):
   - `DATABASE_URL` → reference the Postgres service's `DATABASE_URL`
   - `REDIS_URL` → reference the Redis service's `REDIS_URL`
   - `NEO4J_URI` (e.g. `bolt://neo4j.railway.internal:7687`), `NEO4J_USER`,
     `NEO4J_PASSWORD`
   - `GEMINI_API_KEY`, `FRED_API_KEY`
   - `SEC_USER_AGENT` — must identify a real contact email (SEC fair-use policy)
   - `CORS_ALLOW_ORIGIN_REGEX` if the frontend domain differs from the default
6. Generate a public domain for the backend service.

The backend listens on `$PORT` (Railway injects it; `railway.json`'s
`startCommand` passes it to uvicorn, overriding the Dockerfile's fixed 8000).

## Apply migrations

Point a local shell at the Railway Postgres (paste its `DATABASE_URL` into your
`.env` — see the commented alternate in `.env.example`), then from `backend/`:

```bash
uv run --env-file ../.env alembic upgrade head
```

Or run it as a one-off command inside the Railway backend service.

## First live ingestion run

Requires `DATABASE_URL` (Railway Postgres), `FRED_API_KEY`, and an identifying
`SEC_USER_AGENT`. From `backend/`:

```bash
uv run --env-file ../.env python -m riskweave_api.ingestion.cli --snapshot demo-freeze-candidate-1
```

This is rate-limit bound (SEC 10 req/s) and takes a while — start it early and
let it run unattended. Capture the run summary (documents fetched, chunks,
XBRL facts, macro observations, duration) and post it on RIS-8.

## Verify the live path

- `GET https://<backend-domain>/health` returns healthy.
- All four services green in the Railway dashboard.
- One scenario run + WebSocket slider round-trip works against the domain.

## Cost

Stay on the free/hobby tier. Postgres and Redis plugins and one small backend
replica fit comfortably; Neo4j's volume is the main persistent cost. The demo
dataset is small (curated 100–200 entity universe). Do not enable autoscaling or
add replicas.

## Rollback

Everything still runs locally via `docker compose up` unchanged. Changing the
host or switching to a Nixpacks build requires a new ADR amending ADR-008.

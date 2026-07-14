# RiskWeave

Evidence-backed financial contagion and scenario analysis platform.

RiskWeave turns public financial filings, structured company facts, macroeconomic data, and validated company relationships into an interactive map of how shocks can propagate through the financial system.

Describe a financial shock in natural language. RiskWeave parses it into a structured scenario, propagates impact through a curated knowledge graph with deterministic, data-derived edge weights, and renders an interactive graph with a live severity slider and per-edge evidence.

**Scenario packs:** commercial real estate decline (primary), oil price shock (secondary).

## Design invariants

These are non-negotiable (`RW-AI-010`, `RW-ALG-001`, `RW-ALG-032`):

- **Gemini finds the sentence; deterministic code turns it into the number.** Models must not produce or adjust weights, ratios, or magnitudes used in propagation.
- **No edge without provenance.** Every relationship carries source document id, quoted passage with offsets, data timestamp, derivation method id, and extraction confidence.
- **Every edge weight comes from a registered derivation method** (`DER-COMMODITY`, `DER-CONCENTRATION`, `DER-CREDIT`, `DER-DURATION`, `DER-GEO`, `DER-BETA`).
- Explanations may only cite numbers present in the computation payload.
- Runs bind to an immutable data snapshot and are reproducible from snapshot + versions + seed.

The full product and system requirements live in [`RISKWEAVE_MASTER_SPEC_MERGED.md`](./RISKWEAVE_MASTER_SPEC_MERGED.md) (v2.1.0). Agent-oriented repo guidance is in [`CLAUDE.md`](./CLAUDE.md).

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js, TypeScript, Cytoscape.js |
| Backend | Python 3.11+, FastAPI, Pydantic v2, NumPy |
| Data | PostgreSQL, Neo4j, Redis |
| AI | Gemini (Flash for extraction, Pro for shock parsing / explanation) |
| Ingestion | SEC EDGAR, XBRL company facts, FRED (free-tier, rate-limited) |
| Packaging | Docker Compose, GitHub Actions CI |

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [uv](https://docs.astral.sh/uv/) (backend local runs)
- Node.js 20.9+
- Gemini, FRED, and SEC credentials as needed (see `.env.example`)

## Quick start

```powershell
Copy-Item .env.example .env
# Edit .env: set GEMINI_API_KEY, FRED_API_KEY, and SEC_USER_AGENT

docker compose up --build --wait
```

| Service | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| Backend health | http://localhost:8000/health |
| Neo4j Browser | http://localhost:7474 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

Stop the stack with `docker compose down`.

## Local development

### Install

```powershell
Copy-Item .env.example .env

Set-Location backend
uv sync --frozen --dev

Set-Location ..\frontend
npm ci
```

For local (non-Docker) backend runs, point `DATABASE_URL`, `NEO4J_URI`, and `REDIS_URL` in `.env` at `localhost` instead of the Compose service hostnames.

### Backend

From `backend/`:

```powershell
uv run --env-file ../.env uvicorn riskweave_api.main:app --app-dir src --reload
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Batch ingestion (requires `DATABASE_URL`, `FRED_API_KEY`, and an identifying `SEC_USER_AGENT`):

```powershell
uv run python -m riskweave_api.ingestion.cli --snapshot demo-2026-07-11
```

### Frontend

From `frontend/`:

```powershell
npm run dev
npm run lint
npm run format:check
npm test
npm run build
```

## Repository layout

```
backend/          FastAPI API, ingestion, propagation, derivations
frontend/         Next.js workbench and graph UI
data/             Curated entity universe and evaluation fixtures
docs/             ADRs, demo materials, solution notes
scripts/          Operational helpers
workflows/        Agent and feature workflows
```

## Security

Never commit API keys, credentials, or sensitive financial data. Keep secrets server-side only — do not expose them via `NEXT_PUBLIC_*` variables or client logs.

## License

Private project unless otherwise stated.

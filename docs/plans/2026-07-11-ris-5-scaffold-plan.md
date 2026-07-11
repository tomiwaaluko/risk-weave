---
title: RIS-5 monorepo scaffold implementation plan
date: 2026-07-11
ticket: RIS-5
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
requirements: docs/brainstorms/2026-07-11-ris-5-scaffold-requirements.md
---

# RIS-5 monorepo scaffold implementation plan

## Scope boundaries

Implement infrastructure and runnable health surfaces only. Do not introduce RiskWeave domain models, schemas, ingestion, graph logic, or AI behavior.

## Implementation units

### U1 — Backend project

- **Goal:** Create a locked uv-managed FastAPI project with settings validation, a `/health` endpoint, pytest, Ruff, and a container image.
- **Files:** `backend/pyproject.toml`, `backend/uv.lock`, `backend/Dockerfile`, `backend/src/riskweave_api/*`, `backend/tests/*`.
- **Execution note:** Test first: assert the health response before adding the application implementation.
- **Test scenarios:** health endpoint returns HTTP 200 and a stable `{"status":"ok"}` payload; settings reject missing required infrastructure configuration.
- **Verification:** `uv sync --frozen --dev`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`.

### U2 — Frontend project

- **Goal:** Create a locked Next.js TypeScript App Router project with a minimal status page, ESLint, Prettier, Vitest, and a container image.
- **Files:** `frontend/package.json`, `frontend/package-lock.json`, `frontend/Dockerfile`, frontend configuration, `frontend/src/app/*`, `frontend/src/**/*.test.tsx`.
- **Execution note:** Test first: assert the status page contract before adding the component.
- **Test scenarios:** page exposes the RiskWeave name and scaffold-ready state; production build succeeds.
- **Verification:** `npm ci`, `npm run lint`, `npm run format:check`, `npm test -- --run`, `npm run build`.

### U3 — Compose and configuration

- **Goal:** Orchestrate PostgreSQL, Neo4j, Redis, backend, and frontend with persistent volumes, healthchecks, and documented environment configuration.
- **Files:** `docker-compose.yml`, `.env.example`, `.gitignore`, `.dockerignore`, service Dockerfiles.
- **Test scenarios:** Compose config resolves with example values; dependencies use `service_healthy`; no Gemini key is exposed to frontend; all five services define healthchecks.
- **Verification:** `docker compose config`; build and start the stack when the local Compose plugin is available; inspect service health.

### U4 — CI and contributor commands

- **Goal:** Add PR CI for both projects and replace the placeholder repository guidance with exact commands.
- **Files:** `.github/workflows/ci.yml`, `CLAUDE.md`, directory placeholders.
- **Test scenarios:** workflow YAML parses; commands match package scripts and uv tasks; secret scan is clean.
- **Verification:** run the complete local command set, inspect the workflow, and run a tracked-file secret-pattern scan.

## System-wide checks

- Backend settings consume only server-side environment variables.
- Frontend receives no `GEMINI_API_KEY` or `NEXT_PUBLIC_*` secret.
- Compose startup ordering follows PostgreSQL/Neo4j/Redis health before backend and backend health before frontend.
- Lockfiles are committed and CI uses frozen installs.

## Acceptance trace

- Five healthy Compose services: U1–U3 (`RW-NFR-003/004/005`).
- Green PR lint and tests: U1, U2, U4.
- No repository secret and server-only Gemini configuration: U3–U4 (`RW-SEC-001/004`).
- Real commands in `CLAUDE.md`: U4.

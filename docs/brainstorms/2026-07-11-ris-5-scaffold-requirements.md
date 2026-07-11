---
title: RIS-5 scaffold requirements
date: 2026-07-11
ticket: RIS-5
artifact_contract: ce-requirements/v1
---

# RIS-5 scaffold requirements

## Outcome

Create the smallest reproducible monorepo foundation that every RiskWeave implementation ticket can build on, without adding product logic.

## Requirements

- Provide `backend/`, `frontend/`, `docs/adr/`, `docs/solutions/`, and `scripts/` roots.
- Use Python 3.11+, FastAPI, Pydantic v2, uv, pytest, Ruff, and four-space Python formatting.
- Use Next.js, TypeScript, ESLint, Prettier, Vitest, and two-space TypeScript formatting.
- Define PostgreSQL, Neo4j, Redis, backend, and frontend in Docker Compose with persistent database volumes and health-based startup ordering.
- Document every runtime variable in `.env.example`; keep Gemini credentials server-side and ignore all real environment files.
- Run backend and frontend lint, formatting checks, tests, and builds in GitHub Actions on pull requests.
- Document exact install, run, lint, test, build, and Compose commands in `CLAUDE.md`.

## Success criteria

- A clean checkout can be configured by copying `.env.example` to `.env` and can start all five healthy services with Docker Compose.
- Backend and frontend each have a real health endpoint/page and a focused passing test.
- CI uses committed lockfiles and fails on lint, formatting, test, or build regressions.
- A repository scan finds no committed secret or frontend-exposed Gemini key.

## Scope boundaries

- No application domain logic, persistence schema, migrations, ingestion, graph assembly, or Gemini calls.
- No Kafka, Kubernetes, Supabase, cloud deployment, or optional TimescaleDB extension.
- Health endpoints exist only to support deterministic orchestration.

## Traceability

Enabling work for `RW-NFR-003`, `RW-NFR-004`, `RW-NFR-005`, `RW-SEC-001`, and `RW-SEC-004`, following spec sections 14, 18, and 25.

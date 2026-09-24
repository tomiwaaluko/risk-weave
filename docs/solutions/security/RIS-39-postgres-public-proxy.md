# RIS-39 — Railway Postgres public TCP proxy removal

Date: 2026-09-24  
Linear: [RIS-39](https://linear.app/risk-weave/issue/RIS-39/railway-postgres-is-publicly-reachable-via-tcp-proxy-5432)  
Finding: F1 from [RIS-35](https://linear.app/risk-weave/issue/RIS-35/security-review-pass-for-the-live-deployment-rw-sec-001004) live-deployment security review  
Related doc: `docs/solutions/security/RIS-35-live-deployment-security-review.md` §4 (not modified by this ticket)

## Problem

The Railway **Postgres** service exposed a public TCP proxy on application port **5432**. The financials / provenance / time-series store was reachable from the internet; only the database password gated access. Backend and ingestion already use Railway private networking (`*.railway.internal`), so the public proxy was unnecessary exposure.

## Actions taken (2026-09-24)

| Check | Result |
| --- | --- |
| Public TCP proxy on Postgres :5432 | **Removed** — list-tcp-proxies reports no proxies for Postgres in production |
| Private `DATABASE_URL` on backend / ingestion | **Confirmed** — both use reference `${{Postgres.DATABASE_URL}}`; rendered host is `*.railway.internal` (not `*.proxy.rlwy.net`) |
| Postgres password rotated after exposure | **Rotated** — `ALTER USER` on role `postgres` over private networking; `POSTGRES_PASSWORD` updated on the Postgres service so reference consumers pick up the new value; temporary one-shot rotator service deleted afterward |
| Backend health after rotation | **Succeeded** — `GET https://backend-production-b2dc.up.railway.app/health` returned `200` with `{"status":"ok"}` |
| Redis TCP proxy | **Not touched** (owned by RIS-40) |

Operational changes were made in Railway only. This repository change is the audit record.

## Verification

1. `list-tcp-proxies` for Postgres → no public proxies.
2. Unrendered variable inspection: backend and ingestion `DATABASE_URL` → `${{Postgres.DATABASE_URL}}`; Postgres `DATABASE_URL` → private-domain template using `RAILWAY_PRIVATE_DOMAIN`.
3. Backend redeploy after password variable sync → deployment `SUCCESS`; health endpoint `200 {"status":"ok"}`.

## Out of scope / notes

- Neo4j remains private-only (already correct posture per RIS-35).
- `DATABASE_PUBLIC_URL` may still exist as a Postgres template variable; with no TCP proxy it is not a live public endpoint.
- No secrets, passwords, or connection strings are recorded in this document.

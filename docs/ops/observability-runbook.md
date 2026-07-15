# Observability Runbook (RIS-33)

Operational floor for the Railway-hosted backend: where logs live, what each
alert means, and how to roll back a bad deploy. Companion to
[ADR-008](../adr/ADR-008-railway-primary-host.md) (Railway hosting) and spec
§15 (evaluation-dashboard latency metrics).

## Where logs live

- **Railway dashboard** → the `backend` service → **Deployments** → select a
  deployment → **Logs**. This is stdout of the running container.
- Every line is a single JSON object (see `backend/src/riskweave_api/observability/logging_config.py`):

  ```json
  {"timestamp": "2026-07-15T12:00:00+00:00", "level": "INFO", "logger": "riskweave_api.request",
   "message": "request", "request_id": "a1b2c3d4", "method": "GET", "path": "/health",
   "status": 200, "duration_ms": 3.2}
  ```

- `LOG_LEVEL` (env var, default `INFO`) controls verbosity. Set to `DEBUG` on
  Railway temporarily to see per-request cache-hit/miss detail; revert after
  debugging (`DEBUG` is noisier and costs more log-retention quota).
- Every emitted line is passed through a secret-scrubbing filter before
  formatting (`scrub_secrets` + a named-field redaction list covering
  `api_key`, `password`, `*_url`, `token`, `authorization`, etc.) — see
  `RW-SEC-001` below.

## What each alert means

| Signal | Meaning | First action |
| --- | --- | --- |
| Railway health check failing (`healthcheckPath: /health` in `railway.json`) | Process is down or not accepting connections | Check **Logs** for a crash/exception at startup; check the **Deployments** tab for a failed build; roll back (below) if the previous deployment was healthy |
| External uptime pinger reports `/health` unreachable | Full path (DNS/edge/Railway) is down, not just the process | Check Railway status page, then the service's own health check state |
| A log line with `"logger": "riskweave_api.request"` and `"status" >= 500` | An endpoint returned a server error | Filter logs for the same `request_id` to find the paired `"unhandled exception"` line (includes a scrubbed traceback) and the failing `path` |
| A log line with `"message": "unhandled exception"` | A route raised without its own error handling | Read the `exception` field; cross-reference `request_id` against the request log line for `method`/`path`/`duration_ms` |
| `{"component": "redis", "state": "unavailable"}` at startup | Redis was unreachable when the process booted; the service is running **uncached/degraded**, not down (`RW-NFR-004` is best-effort) | Check the Redis plugin in the Railway project; a mid-session Redis outage after a successful startup will instead surface as 500s on cache-touching endpoints (see the row above) |
| `{"component": "redis", "state": "connected"}` | Redis came up normally | No action; informational |
| `{"component": "postgres", "state": "unavailable"}` at startup | The `postgres` `ScenarioStore` backend (Railway/ADR-008) could not run `SELECT 1` | Scenario creation/persistence/run listing will 500 until this clears; check the Postgres plugin and `DATABASE_URL` |
| p95 in `GET /metrics/latency` → `histograms.propagation_recompute.p95_ms` exceeds `budget_ms.propagation_recompute` (500 ms) | `RW-NFR-002`'s slider-recompute budget is being missed in production | Check node/edge count for the active snapshot, Redis cache-hit rate, and Railway instance sizing |

## Latency metrics (`RW-NFR-002`, spec §15)

`GET /metrics/latency` (unauthenticated, same trust level as `/health`)
returns p50/p95/count for three in-process histograms, each backed by a
1000-sample ring buffer:

- `scenario_parse` — Gemini shock-parsing calls (`/scenarios/parse/live`,
  `/scenarios/presets/{id}/parse`)
- `propagation_recompute` — the severity-slider round trip (WebSocket) and
  the REST `/scenarios/{id}/run` recompute; checked against the 500 ms
  budget in `budget_ms.propagation_recompute`
- `explanation_generation` — per-node explanation generation

The RIS-21 evaluation dashboard reads this endpoint directly; there is no
Prometheus/Grafana stack (explicitly out of scope for this ticket — revisit
only with evidence a single-histogram-endpoint isn't enough for one Railway
replica, per `RW-NFR-005`).

Histograms reset on every process restart (redeploy, crash-restart) — they
are a rolling production window, not a durable time series. If a persisted
history is needed later, that is a new ticket, not a silent scope add here.

`GET /metrics/connectivity` mirrors the startup connectivity log lines as
polled state (`redis_connected` / `postgres_connected`; `null` means "not
applicable" for that backend), for alerting rules that prefer polling an
endpoint over parsing logs.

## Uptime monitoring setup (one-time, human/dashboard step)

1. **Railway's own check** is already configured in `railway.json`:
   `healthcheckPath: /health`, `healthcheckTimeout: 30`,
   `restartPolicyType: ON_FAILURE` (5 retries). No action needed — this
   restarts a crashed container automatically and is what backs the
   "Railway health check failing" row above.
2. **External pinger** (catches edge/DNS/regional outages Railway's own
   check can't see): the operator picks a free-tier uptime service (e.g.
   UptimeRobot, Better Uptime) and points a 1–5 minute HTTP(S) check at
   `https://<railway-domain>/health`, expecting `200` and
   `{"status": "ok"}`. Configure its alert to email and/or Slack — no
   API keys or webhook URLs for this belong in the repo; they're entered
   directly in the pinger's dashboard.
3. **Error-rate alerting**: Railway → project → the `backend` service →
   **Observability** (or a log drain, if the plan supports one) → add an
   alert rule on `status>=500` or `level=ERROR` frequency (e.g. "5 or more
   in 5 minutes"), notifying the same email/Slack channel. Railway's
   built-in crash/deploy-failure notifications (Project Settings →
   Notifications) should also be enabled — those catch a build/startup
   failure quicker than log-rate alerting would.

## Rolling back a deploy

1. Railway dashboard → `backend` service → **Deployments**.
2. Find the last deployment that was healthy (green health check, no
   error-rate alert).
3. Click it → **Redeploy** (this redeploys that exact image; it does not
   rebuild).
4. Watch **Logs** for a clean startup (`"redis connected"` /
   `"postgres connected"` lines, then a passing `/health` check) before
   considering the incident closed.
5. If the bad deploy included a database migration, a rollback is a *code*
   rollback only — do not run `alembic downgrade` against production without
   a separate, deliberate decision; most schema changes here are additive.

## Secret hygiene spot check (`RW-SEC-001`)

Pull a recent log window and grep for common secret shapes; all matches
below should show `[REDACTED]`, never plaintext:

```powershell
# From the Railway dashboard, export/copy recent logs to a local file, then:
Select-String -Path recent-logs.jsonl -Pattern 'Bearer [A-Za-z0-9]|:[^@]*@|"password"|"api_key"|"gemini_api_key"'
```

If any match shows a real credential instead of `[REDACTED]`, treat it as a
`RW-SEC-001` regression: rotate the exposed credential immediately, then fix
the scrubbing pattern in `backend/src/riskweave_api/observability/logging_config.py`
and add a regression test in `backend/tests/test_observability_logging.py`.

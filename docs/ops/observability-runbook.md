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
| A new deploy fails its healthcheck (`healthcheckPath: /health` in `railway.json`) | The **new** deployment never became healthy within 30 s, so Railway never cut traffic to it — the previous deployment keeps serving. This only fires during a deploy, not continuously (Railway does not poll `/health` after go-live) | Check **Deployments** → the failed deployment's **Logs** for a startup crash/exception; fix and redeploy, or stay on the previous (still-live) version |
| Container crashes/exits at any time | `restartPolicyType: ON_FAILURE` (`railway.json`) restarts it automatically, up to 5 retries — this *is* continuous, but it's process-exit-triggered, not `/health`-triggered (a hung-but-alive process won't trip it) | Check **Logs** around the restart timestamp for the exception that caused the exit |
| External uptime pinger / Uptime Kuma reports `/health` unreachable | Full path (DNS/edge/Railway/process) is down, or the process is alive but not responding — the one signal Railway itself doesn't give you post-deploy | Check Railway's status page, then **Deployments** for the current deployment's state |
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

## Uptime monitoring setup

Verified directly against Railway's own docs (2026-07-15) — corrects an
earlier draft of this runbook that assumed `/health` was polled
continuously; it is not.

1. **Railway's deploy-time check** is already configured in `railway.json`:
   `healthcheckPath: /health`, `healthcheckTimeout: 30`. This only runs
   during a new deploy, to decide whether to cut traffic to it — Railway
   does **not** poll it after go-live. Separately, `restartPolicyType:
   ON_FAILURE` (5 retries) restarts the container any time the process
   crashes/exits, deploy or not. Neither of these catches a process that's
   alive but hung/deadlocked.
2. **Deployment/crash notifications** — **manual step still required**:
   Railway's webhook config (Settings → Webhooks) has no public API, so it
   cannot be set up from this repo or by an agent — confirmed directly
   against the live project (2026-07-15: no webhook-creation mutation is
   exposed to Railway's own MCP tooling). To finish this: open the
   `risk-weave` project → **Settings** → **Webhooks** → paste your Discord
   incoming-webhook URL → **Save Webhook**. Once saved, deploy
   success/failure/crash and resource-monitor alerts post to that channel.
   Follow [Railway's webhook guide](https://docs.railway.com/observability/webhooks)
   if it ever needs to be recreated — never commit the webhook URL itself.
3. **Resource monitors** (CPU/RAM/disk/network-egress thresholds, **Pro
   plan required**): Observability tab → any metric widget → ⋮ → "Add
   monitor". Not yet configured; these also fire through the same webhook
   once set up.
4. **Continuous uptime polling** — **done** (2026-07-15): the Uptime Kuma
   template is deployed as a service (`Uptime Kuma`, service id
   `763a0943-359c-4446-970f-100cebdcaf08`) in the `risk-weave` production
   environment via `railway.com/deploy/p6dsil`. One remaining manual step:
   open its dashboard (Railway → `Uptime Kuma` service → generate a domain
   or open the service) and add a monitor for
   `https://backend-production-b2dc.up.railway.app/health` (HTTP(S), 1–5
   minute interval, expect `200`), then point its notification settings at
   the same Discord webhook. Uptime Kuma's own UI/database isn't managed by
   this repo — that config lives in its persistent volume on Railway, not
   in git.
5. **Error-rate alerting**: confirmed Railway does **not** collect
   application-level metrics (their docs: *"request latency, error rates...
   are not collected by Railway"*). The closest native substitute is a
   filtered **Logs** widget on the Observability dashboard for
   `status>=500`, watched manually, or shipping logs to a third-party tool
   via OpenTelemetry — genuinely out of scope for this ticket per the
   "no Prometheus/Grafana" constraint. Until that's revisited, rely on the
   crash/deploy-failure webhook (item 2) plus the `/metrics/latency` and
   `/metrics/connectivity` endpoints below for spot checks.

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

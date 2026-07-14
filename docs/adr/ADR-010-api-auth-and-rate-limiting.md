# ADR-010: Shared API Key + Per-IP Rate Limiting for the Public Backend

## Status

Accepted for v1 (2026-07-14).

## Context

RIS-31 verified by code reading that the deployed Railway backend
(`ADR-008`) carried zero authentication or rate limiting: `main.py`
registered only CORS middleware, and none of `dependencies.py` or the five
routers (`scenarios`, `slider`, `registry`, `spike`, `graph`) gated a request
on identity or request volume. CORS constrains browsers only, not `curl`.
Concretely, any anonymous client could loop `POST /scenarios/presets/{id}/parse`
and `GET /scenarios/{id}/explanation/{node_id}` — both real Gemini calls — to
exhaust the Gemini quota, mutate in-memory server state via `POST
/spike/seed`, or open unlimited WebSocket slider connections.

The spec predates a public host and defines no auth requirement, so this ADR
adds enabling infrastructure rather than reinterpreting a MUST-level
requirement (spec §0.3). It is adjacent to `RW-SEC-001` (the Gemini key is
already server-side only) and `RW-DATA-005` (provider quota compliance).

## Original Requirement

None directly — the closest anchors are `RW-SEC-001` (keys never reach the
client) and `RW-DATA-005` (respect provider rate limits). ADR-008 established
Railway as the always-on public host this now needs to protect.

## Proposed Change

1. **Static shared bearer key** (`RISKWEAVE_API_KEY`), checked via a
   constant-time compare against `Authorization: Bearer <key>`, gates every
   mutating and Gemini-calling backend endpoint:
   `POST /scenarios`, `POST /scenarios/{id}/validate`, `POST
   /scenarios/{id}/run`, `POST /scenarios/presets/{id}/parse`, `GET
   /scenarios/{id}/explanation/{node_id}`, `POST /graph/seed`, `POST
   /spike/seed`, `POST /spike/run`. `GET /health` and read-only informational
   endpoints (`GET /graph/methodology`, scenario templates/presets lists,
   read-only registry lookups) stay open — deliberately, not by omission.
   When `RISKWEAVE_API_KEY` is unset the gate is a no-op, so local dev, CI,
   and the Docker Compose stack keep working unchanged; Railway production
   always sets it.
2. **Per-IP token-bucket rate limiting**, in-process (`riskweave_api.security`):
   a tight budget (burst 5, ~5/minute sustained) on the two Gemini-calling
   endpoints, and a looser budget (burst 30, ~60/minute sustained) on
   everything else including the registry tool-call surface. Disableable via
   `RATE_LIMIT_ENABLED` for local load testing.
3. **WebSocket slider hardening**: a process-wide connection cap
   (`MAX_SLIDER_CONNECTIONS = 200`) rejects new connections past the cap with
   close code 4029, and each connection gets its own token-bucket message
   throttle (burst 20, 10/sec sustained) so a single anonymous connection
   cannot flood recomputes past the ≤500 ms budget (`RW-NFR-002`). The
   WebSocket itself stays unauthenticated — the scenario it drives can only
   have been created through an already-gated REST call, so this is a
   deliberate, narrower control (IP-based, not key-based) rather than a gap.
4. **Frontend key delivery**: a same-origin Next.js route handler
   (`frontend/src/app/api/backend/[...path]`) proxies REST calls, attaching
   `RISKWEAVE_API_KEY` from a server-side-only env var. Client components
   call the proxy path (`/api/backend/...`), never the raw backend origin,
   so the key never enters the client bundle (`RW-SEC-001`). The WebSocket
   slider connects directly to the backend (proxying a persistent WS through
   a serverless route handler is impractical), consistent with point 3.
5. **Spike surface**: the backend `/spike` router stays mounted — the
   production root page (`/`) depends on `POST /spike/seed` for its graph —
   but its endpoints are now gated like any other mutating endpoint. The
   standalone frontend `/spike` demo page (RIS-15, superseded by `/` and
   `/graph`) is excluded from a default production build (`ENABLE_SPIKE_PAGE`
   unset → `notFound()`), reachable only when explicitly opted into for local
   development.
6. `401`/`429` responses carry only a generic `detail` string — no stack
   trace, no key material, no internal path.

## Reason

Per spec §0.4 (financial correctness > evidence provenance > user trust >
reproducibility > reliable demo behavior > **simplicity** > performance >
cost > extensibility), a single shared key plus in-process token buckets is
the simplest mechanism that closes the actual exposure — no user accounts,
no session state, no external rate-limiting service, no Kafka/Kubernetes
(prohibited, spec §5.3). It costs nothing to operate and requires no new
infrastructure on Railway's free tier. Making the gate a no-op when the key
is unset preserves every existing local/CI/Compose workflow without adding
environment-detection branching.

## Alternatives Considered

- **Full user accounts / OAuth / entitlements**: rejected — explicitly out of
  scope (`RW-DATA-D12`, DEFERRED); massive scope increase for a hackathon
  demo with one legitimate client (the Vercel frontend).
- **slowapi / a rate-limiting library**: considered and installed, then
  reverted. It couples rate limiting to a global `Limiter` on `app.state`
  with its own exception-handler wiring and decorator-based `Request`
  plumbing, which is harder to reset cleanly between tests than a small
  dependency-injected token bucket and adds a dependency for ~80 lines of
  logic already needed anyway.
- **Redis-backed distributed rate limiting**: rejected for v1 — single
  Railway instance, demo scale; in-process state is simpler and Redis
  unavailability already degrades gracefully elsewhere in this codebase.
  Revisit if the backend is ever horizontally scaled.
- **Disabling the `/spike` backend router entirely**: rejected — the
  production root page's graph load depends on `POST /spike/seed`; removing
  it would break a live user-facing flow. Gating it behind the same API key
  as other mutating endpoints achieves the security goal without breaking
  that dependency.
- **Proxying the WebSocket through the Next.js route handler**: rejected —
  persistent connections don't fit the serverless route-handler model
  cleanly; IP-based connection/message throttling on a REST-gated scenario
  is a proportionate narrower control instead.

## Consequences

Anonymous `curl` against `POST /scenarios`, the preset parser, or the
explanation endpoint now gets `401` once Railway sets `RISKWEAVE_API_KEY`.
Legitimate frontend traffic is unaffected because it now goes through the
same-origin proxy. Sustained scripted abuse of the Gemini-calling endpoints
is capped at ~5/minute per IP regardless of the key (defense in depth against
a leaked key). Operators must set `RISKWEAVE_API_KEY` identically in the
Railway backend service and the Vercel frontend project for the proxy to
authenticate; forgetting the frontend side degrades to `401`s in the UI
(caught and surfaced by existing error states), not a silent bypass.

## User And Judging Impact

No visible change to the demo flows — the frontend proxy makes the key
transfer invisible. A judge inspecting the client bundle or network tab sees
no key; a judge running `curl` against the bare Railway URL now sees `401`
instead of a working Gemini call.

## Security, Data, Cost, And Performance Impact

Closes the open-proxy-to-Gemini and anonymous-state-mutation exposures
RIS-31 identified. No secrets added to the repo, client bundle, or logs
(`RW-SEC-001/004` — verified by spot check: the key is read only from
`Settings`/`process.env` server-side). Rate limiting bounds worst-case
Gemini spend and CPU from anonymous traffic. Token-bucket checks are O(1) and
negligible against the ≤500 ms slider budget (`RW-NFR-002`).

## Migration Or Rollback

Unsetting `RISKWEAVE_API_KEY` restores today's open behavior instantly (no
code rollback needed) — useful for an emergency demo if the key is lost.
Setting `RATE_LIMIT_ENABLED=false` disables rate limiting the same way.
Rolling back the mechanism itself means reverting the `riskweave_api.security`
module, its call sites, and the frontend proxy route.

## Human Approval Required

Yes — generating and setting `RISKWEAVE_API_KEY` identically in the Railway
backend service and the Vercel frontend project's environment variables is a
human-operated step (no Railway/Vercel MCP write access assumed here).

No MUST-level requirement is weakened by this ADR; it adds infrastructure the
spec did not anticipate needing (a public host) without touching propagation,
provenance, or explanation guarantees.

## Affected Requirements

`RW-SEC-001`, `RW-SEC-004`, `RW-DATA-005`, `RW-NFR-002`. Extends ADR-008
(Railway host) with the access-control layer that host needed.

## Sources

- FastAPI dependency injection for cross-cutting auth/rate-limit checks:
  https://fastapi.tiangolo.com/tutorial/dependencies/
- Token bucket algorithm: standard rate-limiting technique, no external
  reference required for this in-process implementation.

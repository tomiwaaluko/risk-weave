# Perf Workflow

**Branch:** `perf/<ticket-id>-<short-slug>`
**Use when:** the ticket targets latency, throughput, or resource usage.
Rule number one: **measure before and after** — no optimization ships without numbers.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`). Extract the target metric and
   threshold (e.g., "slider recompute ≤500 ms"). If the ticket has no measurable
   target, comment on it asking for one before starting.
2. `mem-search` + `docs/solutions/` — past perf work often documents the hot paths.
3. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

Measurement tooling first (catalog in `../README.md`):

- **Railway / Vercel MCP** — production metrics: response times, error rates, logs.
- **claude-in-chrome** — frontend perf: network waterfall, console timing.
- **Supabase MCP** — query plans and database advisors for data-layer slowness.
- Local profilers per stack (e.g., `cProfile`/`py-spy` for Python, DevTools for JS).

## Phase 2 — Baseline & diagnose

1. Reproduce the slowness and record a **baseline measurement** with the exact
   command/scenario so the after-measurement is comparable.
2. Profile to find the actual bottleneck. Do not optimize on intuition — the
   profiler decides where the time goes.

## Phase 3 — Optimize

3. `/ce-optimize` — apply the improvement on `perf/<ticket-id>-<slug>`, targeting
   only the measured bottleneck. One optimization per commit, re-measured each time.
4. `/ce-simplify-code` — perf code rots fastest; keep it as clear as the speedup
   allows, and comment any non-obvious trick with the measurement that justifies it.

## Phase 4 — Review & verify

5. `/ce-code-review` — reviewers check correctness under the optimization
   (caching invalidation, concurrency, precision) — the classic perf-bug zoo.
6. Confirm: after-measurement meets the ticket's threshold, and the full test
   suite is still green (optimizations must not change results).

## Phase 5 — Ship & close

7. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>` and includes the
   before/after numbers and measurement method.
8. Update the Linear ticket: link PR, comment the numbers, move to **In Review**.
9. `/ce-compound` — document the bottleneck pattern and profiling method.

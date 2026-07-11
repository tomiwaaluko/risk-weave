# Hotfix Workflow

**Branch:** `hotfix/<ticket-id>-<short-slug>` (branched from the production branch)
**Use when:** production is broken or degraded and speed matters. This is the
expedited path: smallest safe change, ceremony deferred until after the fire is out.

## Phase 0 — Ticket intake (fast)

1. Fetch the Linear ticket (Linear MCP `get_issue`) — read only enough to understand
   impact and reproduction. Move to **In Progress** immediately.
2. Comment on the ticket that a hotfix is underway, so humans watching know.

## Phase 1 — Tool & MCP survey (production-facing)

Load observability tools first — the bug lives in production:

- **Railway / Vercel MCP** — deployment status, runtime logs, error rates.
- **Supabase MCP** (`get_logs`) — if data-layer.
- **claude-in-chrome** — reproduce user-facing breakage directly.

## Phase 2 — Diagnose (time-boxed)

1. `/ce-debug` — abbreviated: reproduce and identify the offending change fast.
   `git log` against the last known-good deploy is often the shortest path.
2. **Decision point:** if a clean `git revert` of the offending commit restores
   service, prefer it — switch to the **revert** workflow and do the real fix as a
   follow-up **bugfix** ticket. Only hand-craft a hotfix when revert isn't viable.

## Phase 3 — Minimal fix

3. On `hotfix/<ticket-id>-<slug>`, make the smallest change that restores correct
   behavior. No refactoring, no drive-by cleanup. Add a regression test if it takes
   minutes, not hours; otherwise file a follow-up ticket for it.

## Phase 4 — Focused review & ship

4. `/ce-code-review` — focused pass on the diff only; blast-radius check.
5. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>`, states impact,
   root cause (if known), and rollback plan. Flag it for expedited merge.
6. After merge/deploy, verify recovery with the same observability tools from
   Phase 1 (logs clean, error rate down, flow works).

## Phase 5 — Close & learn

7. Update the Linear ticket: link PR, comment the incident timeline
   (broke → detected → fixed → verified), move to **Done** once verified in prod.
8. File follow-up tickets for anything deferred (proper test, underlying cleanup).
9. `/ce-compound` — mandatory for hotfixes: capture how it broke and how detection
   or tests could have caught it earlier.

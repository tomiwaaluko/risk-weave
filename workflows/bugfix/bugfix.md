# Bugfix Workflow

**Branch:** `bugfix/<ticket-id>-<short-slug>`
**Use when:** the ticket reports a reproducible defect whose root cause must be
found. Root-cause discipline is the core of this workflow — never patch symptoms.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`). Extract reproduction steps,
   expected vs. actual behavior, environment, and any stack traces or screenshots.
2. `mem-search` + `docs/solutions/` — check whether this bug (or its pattern) has
   been solved before. A documented prior solution can short-circuit the whole hunt.
3. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

Pick debugging surfaces based on where the bug lives (catalog in `../README.md`):

- **claude-in-chrome** — frontend bugs: console messages, network requests, DOM state.
- **Supabase MCP** (`get_logs`, `get_advisors`) — database or backend-data bugs.
- **Railway / Vercel MCP** — runtime logs for deployed-environment bugs.
- **Codex plugin** (`codex:rescue`) — second diagnosis pass if you get stuck.

## Phase 2 — Root cause

1. `/ce-debug` — reproduce the failure first, then trace to root cause. Do not
   write a fix until you can state the root cause in one sentence and have a
   failing test that demonstrates it.

## Phase 3 — Fix

2. On `bugfix/<ticket-id>-<slug>`, make the failing test pass with the minimal
   correct fix. Check for other call sites with the same defect pattern.
3. `/ce-simplify-code` — if the fix touched more than a couple of lines.

## Phase 4 — Review & verify

4. `/ce-code-review` — review against the root cause, not just the diff.
5. Re-run the original reproduction steps from the ticket to confirm the bug is
   gone, plus the full test suite for regressions.

## Phase 5 — Ship & close

6. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>`, states the root cause,
   the fix, and the regression test added.
7. Update the Linear ticket: link PR, comment the root-cause summary (future
   searchers will thank you), move to **In Review**.
8. `/ce-compound` — bugs are the highest-value learnings; document the root-cause
   pattern in `docs/solutions/` unless it was trivial.

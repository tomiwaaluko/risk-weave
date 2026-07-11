# Fix Workflow

**Branch:** `fix/<ticket-id>-<short-slug>`
**Use when:** the ticket is a small correction that is *not* a reproducible defect —
wrong copy, off-by-one config, bad default, broken link, minor behavior tweak.
For a reproducible bug with unknown root cause, use the **bugfix** workflow instead.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`); read description and comments.
2. Check `docs/solutions/` and `mem-search` — small fixes are often repeats.
3. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

Small fixes usually need only Linear + git/`gh`. Add from the `../README.md` catalog
only if the ticket clearly touches them (e.g., **claude-in-chrome** to confirm a UI
fix visually, **Supabase MCP** for a data-side correction).

## Phase 2 — Fix

1. Locate the change site. No plan doc needed — the ticket is the spec. If the scope
   turns out bigger than expected, stop and restart under **feature** or **refactor**.
2. Make the correction on `fix/<ticket-id>-<slug>`. Add or adjust a test that pins
   the corrected behavior.
3. `/ce-simplify-code` — only if the fix grew beyond a few lines.

## Phase 3 — Review & verify

4. `/ce-code-review` — quick pass; findings should be near-zero for a true fix.
5. Verify the corrected behavior directly (run the flow, not just the test).

## Phase 4 — Ship & close

6. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>` and states the
   before/after behavior in one sentence each.
7. Update the Linear ticket: link PR, move to **In Review**.
8. `/ce-compound` — only if the fix revealed something non-obvious; skip otherwise.

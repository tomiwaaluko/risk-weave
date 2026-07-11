# Revert Workflow

**Branch:** `revert/<ticket-id>-<short-slug>`
**Use when:** a merged change must be backed out — it broke something, shipped
prematurely, or a decision was reversed. Speed and cleanliness over cleverness:
`git revert`, never history rewriting on shared branches.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`). Identify *exactly* what to back
   out: the offending PR/commit SHA(s) and the observable reason. If the ticket
   doesn't name the commit, find it first (`git log`, `gh pr list --state merged`,
   deploy timeline via Railway/Vercel MCP) — reverting the wrong commit doubles
   the damage.
2. Move the ticket to **In Progress**; comment on the *original* PR/ticket that a
   revert is in flight so its author knows.

## Phase 1 — Tool & MCP survey

- **`gh` CLI** — locate the merged PR, its commits, and CI evidence of breakage.
- **Railway / Vercel MCP** — correlate the breakage with the deploy timeline.
- Everything else stays unloaded — reverts should be minimal.

## Phase 2 — Revert

1. On `revert/<ticket-id>-<slug>`: `git revert <sha>` (or `git revert -m 1 <merge-sha>`
   for merge commits). Resolve conflicts minimally — a revert that needs creative
   conflict resolution deserves extra review scrutiny.
2. Do **not** bundle fixes or improvements into the revert. The revert restores the
   old state; the real fix is a separate **bugfix** ticket.

## Phase 3 — Verify

3. Full test suite green, and confirm the specific breakage from the ticket is gone
   (reproduce the failure scenario against the reverted tree).

## Phase 4 — Ship & close

4. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>`, names the reverted
   PR/commit, states why, and links the follow-up ticket for the proper fix.
   Flag for expedited merge if production is affected.
5. Update the Linear ticket: link PR, move to **In Review** (or **Done** once the
   revert is deployed and verified). Create the follow-up **bugfix** ticket in
   Linear if it doesn't exist, and link both directions.
6. `/ce-compound` — capture why the original change had to be backed out and what
   gate (test, review focus, staging step) would have caught it.

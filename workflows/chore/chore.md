# Chore Workflow

**Branch:** `chore/<ticket-id>-<short-slug>`
**Use when:** maintenance work with no product behavior change — dependency updates,
config housekeeping, tooling upkeep, renaming files, cleaning dead code.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`); move to **In Progress**.
2. Quick `docs/solutions/` check — recurring chores often have documented gotchas
   (e.g., "last time we bumped X, Y broke").

## Phase 1 — Tool & MCP survey

Usually just Linear + git/`gh`. Add **Context7 / docs researchers** for dependency
upgrades (changelogs, breaking-change notes) and **Railway / Vercel MCP** if the
chore touches deploy config or environment variables.

## Phase 2 — Execute

1. Do the chore on `chore/<ticket-id>-<slug>`. For dependency updates: read the
   upstream changelog for breaking changes *before* bumping, upgrade in small
   batches, run the suite between batches.
2. Keep the diff mechanical and reviewable — one kind of change per commit.

## Phase 3 — Verify

3. Full test suite + lint + build. For dep bumps, also boot the app and click
   through one critical flow — suites don't catch everything a major bump breaks.

## Phase 4 — Ship & close

4. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>` and lists exactly what
   changed (e.g., version table for dep bumps) and what was verified.
5. Update the Linear ticket: link PR, move to **In Review**.
6. `/ce-compound` — only if the chore surfaced a gotcha worth documenting.

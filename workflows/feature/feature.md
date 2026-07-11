# Feature Workflow

**Branch:** `feature/<ticket-id>-<short-slug>`
**Use when:** the ticket adds a new user-facing capability or meaningful new behavior.
This is the full compound-engineering loop.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`). Read the description, comments,
   attachments, and any linked docs or Figma files.
2. Search past knowledge before writing anything: `mem-search` for prior sessions and
   `docs/solutions/` for documented learnings that touch this area.
3. Move the ticket to **In Progress** and assign yourself.

## Phase 1 — Tool & MCP survey

Identify what this feature touches and load only the MCPs/plugins you need
(catalog in `../README.md`). Typical for features:

- **Figma MCP** if the ticket links a design.
- **Supabase MCP** if it needs schema or migration changes.
- **claude-in-chrome** if it has a UI you must verify in a browser.
- **Context7 / docs researchers** for any unfamiliar library the plan will pull in.

## Phase 2 — Brainstorm

1. `/ce-brainstorm` — explore requirements against the ticket. Resolve ambiguity by
   commenting questions on the Linear ticket rather than guessing; output a
   requirements document.

## Phase 3 — Plan

2. `/ce-plan` — turn the requirements into an implementation-ready plan.
3. `/ce-doc-review` — persona review of the plan if the feature is large
   (touches >3 files or introduces a new abstraction). Skip for small features.

## Phase 4 — Build

4. `/ce-worktree` — create an isolated worktree on `feature/<ticket-id>-<slug>`.
5. `/ce-work` — execute the plan with task tracking. Write tests alongside the code.
6. `/ce-simplify-code` — refine the freshly written code for clarity and reuse
   before anyone reviews it.

## Phase 5 — Review & verify

7. `/ce-code-review` — multi-agent review against the plan. Address findings.
8. Verify end-to-end: run the real flow, not just the tests (use claude-in-chrome
   for UI features). Capture a demo with `/ce-demo-reel` if the change is visible.

## Phase 6 — Ship & close

9. `/ce-commit-push-pr` — commit, push, open the PR. Body cites
   `Closes <TICKET-ID>`, requirement IDs, tests run, and the demo if captured.
10. Update the Linear ticket: link the PR, comment a summary of what shipped and any
    scope changes, move to **In Review**.
11. `/ce-compound` — document what you learned so the next feature starts smarter.

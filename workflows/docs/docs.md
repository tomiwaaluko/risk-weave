# Docs Workflow

**Branch:** `docs/<ticket-id>-<short-slug>`
**Use when:** the ticket changes documentation only — READMEs, guides, ADRs,
code comments, API docs. No production code changes ride on a docs branch.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`); identify the audience
   (new contributor? API consumer? future agent?) — it dictates tone and depth.
2. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

- **Notion / Google Drive MCP** — if source material or the canonical doc lives there.
- **Context7 / docs researchers** — when documenting integration with an external tool.
- Otherwise Linear + git/`gh` is enough.

## Phase 2 — Write

1. Read the code/behavior you're documenting *first* — docs must describe what the
   system actually does, not what the ticket author remembers it doing. Run
   commands and examples before writing them down.
2. Write on `docs/<ticket-id>-<slug>`. Every example must be copy-paste runnable;
   every referenced path, flag, and requirement ID must exist.

## Phase 3 — Review

3. `/ce-doc-review` — persona review for substantial documents (guides, ADRs,
   specs). Skip for one-line corrections.
4. Verify all links resolve and all code samples execute.

## Phase 4 — Ship & close

5. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>` and states which
   examples/commands were actually executed during verification.
6. Update the Linear ticket: link PR, move to **In Review**.
7. `/ce-compound` — skip unless the writing exposed a doc-structure decision worth
   keeping (e.g., "ADRs live in docs/adr/, numbered").

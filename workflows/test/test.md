# Test Workflow

**Branch:** `test/<ticket-id>-<short-slug>`
**Use when:** the ticket adds or improves tests only — coverage gaps, flaky-test
fixes, test infrastructure. Production code changes belong in other workflows
(finding a real bug while writing tests → file a **bugfix** ticket).

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`); identify what behavior needs
   coverage and why it matters (regression risk, spec requirement, flake pain).
2. For this repo: check the spec requirement IDs the tests should trace to.
3. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

- **claude-in-chrome** — browser-level E2E tests or verifying UI behavior to encode.
- **Supabase MCP** — inspecting real schema/data shapes to build fixtures against.
- Otherwise Linear + git/`gh`.

## Phase 2 — Plan the coverage

1. `/ce-plan` — lightweight: enumerate the behaviors to cover, name each test by
   observable behavior (`test_rejects_edge_without_provenance`), decide unit vs.
   integration per behavior. For flaky tests, root-cause the flake with
   `/ce-debug` before touching anything.

## Phase 3 — Write

2. On `test/<ticket-id>-<slug>`, write the tests. Each new test must **fail** when
   the behavior it pins is broken — verify this by mutating the code under test
   once, watching it fail, then restoring. A test that can't fail is decoration.
3. Keep fixtures minimal and local; avoid coupling tests to implementation details.

## Phase 4 — Review & verify

4. `/ce-code-review` — the testing reviewer checks assertion strength and brittleness.
5. Full suite green; run new tests repeatedly (e.g., 10×) if flake-adjacent.

## Phase 5 — Ship & close

6. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>`, lists behaviors now
   covered, and maps tests to requirement IDs.
7. Update the Linear ticket: link PR, move to **In Review**.
8. `/ce-compound` — document testing patterns worth reusing (fixture strategies,
   flake root causes).

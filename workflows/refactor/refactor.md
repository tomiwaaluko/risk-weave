# Refactor Workflow

**Branch:** `refactor/<ticket-id>-<short-slug>`
**Use when:** the ticket restructures code — extracting modules, renaming, reducing
coupling, paying down debt — with **no intended behavior change**. Behavior
preservation is the invariant every step protects.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`); understand *why* the refactor
   is wanted (velocity, clarity, upcoming feature) — the why shapes how far to go.
2. `mem-search` + `docs/solutions/` — prior architectural decisions may constrain
   or already prescribe the target shape.
3. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

Refactors are mostly repo-local: Linear + git/`gh` usually suffice. Add
**Context7 / docs researchers** if migrating to a new library idiom, and
**claude-in-chrome** if you need before/after verification of UI behavior.

## Phase 2 — Plan

1. `/ce-plan` — map the target structure, the ordered sequence of safe moves, and
   the test coverage that proves behavior is preserved. If coverage is thin over
   the code being moved, add characterization tests *first*.
2. `/ce-doc-review` — only for large structural refactors (new module boundaries,
   changed public interfaces).

## Phase 3 — Execute

3. `/ce-worktree` — isolate on `refactor/<ticket-id>-<slug>`.
4. `/ce-work` — execute in small, individually-green commits: every commit compiles
   and passes the full suite. Never mix a behavior change into a refactor commit —
   if you find a bug mid-refactor, file a ticket or fix it in a separate commit.
5. `/ce-simplify-code` — the core skill here; run it hard. The refactor isn't done
   until the result is simpler than the starting point, not just different.

## Phase 4 — Review & verify

6. `/ce-code-review` — reviewers confirm: no behavior change, coupling reduced,
   nothing renamed into ambiguity.
7. Full test suite green; diff of any public API surfaces is empty or ticketed.

## Phase 5 — Ship & close

8. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>`, states the structural
   before/after, and explicitly claims "no behavior change" with the evidence.
9. Update the Linear ticket: link PR, move to **In Review**.
10. `/ce-compound` — record the new structure and the pattern that motivated it so
    future code lands in the right shape.

# Release Workflow

**Branch:** `release/<version>` (e.g., `release/v1.2.0`)
**Use when:** the ticket is a version cut: freeze scope, verify, document, tag, ship.
No new features enter through this branch — only release mechanics and last-mile fixes.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`). Confirm the target version and
   the scope: list the Linear tickets/PRs going into this release
   (Linear `list_issues` filtered by cycle/project helps assemble this).
2. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

- **Linear MCP** — enumerate shipped tickets for the changelog.
- **`gh` CLI** — merged PRs since last tag, CI status, tagging, GitHub release.
- **Railway / Vercel MCP** — deployment targets and post-deploy verification.
- **claude-in-chrome** — smoke-test the deployed release.

## Phase 2 — Prepare

1. Cut `release/<version>` from `main`. Verify the tree is what you intend to ship
   (`git log <last-tag>..HEAD`).
2. Bump version numbers everywhere they live (package manifests, docs, API version).
3. Write the changelog: derive entries from merged PRs and their Linear tickets;
   group by added/changed/fixed. Human-readable value statements, not commit subjects.

## Phase 3 — Verify

4. Full test suite + lint + build from clean checkout.
5. `/ce-code-review` — review the release diff itself (version bumps, changelog,
   any last-mile fixes); confirms nothing unintended rode along.
6. Smoke-test the critical user flows on a staging/preview deploy
   (Railway/Vercel MCP for deploy, claude-in-chrome to exercise the flows).

## Phase 4 — Ship

7. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>`, the changelog, and the
   verification evidence.
8. After merge: tag the release (`git tag v<version>` + push), create the GitHub
   release with the changelog (`gh release create`), deploy, and verify production.

## Phase 5 — Close

9. Update the Linear ticket: link PR/tag/release URL, comment the deploy
   verification result, move to **Done**.
10. `/ce-compound` — note anything that made this release harder than it should
    have been; feed it into the next cycle.

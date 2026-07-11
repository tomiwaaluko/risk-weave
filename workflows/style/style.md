# Style Workflow

**Branch:** `style/<ticket-id>-<short-slug>`
**Use when:** formatting, lint compliance, naming-convention sweeps — changes with
**zero behavior or logic impact**. The lightest workflow in the set.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`); move to **In Progress**.

## Phase 1 — Tool & MCP survey

Linear + git/`gh` only. Style work never needs external MCPs — if you find yourself
reaching for one, the ticket probably isn't a style ticket.

## Phase 2 — Apply

1. On `style/<ticket-id>-<slug>`, prefer running the repo's formatter/linter with
   autofix over hand-editing — mechanical tools produce mechanical, trustworthy diffs.
2. Never mix a logic change in. If the linter flags a real bug, file a **bugfix**
   ticket and leave that line alone here.
3. One tool/rule per commit (e.g., "apply black", "fix eslint import-order") so the
   diff stays verifiable at a glance.

## Phase 3 — Verify

4. Full test suite green (proves zero behavior change), lint clean.

## Phase 4 — Ship & close

5. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>`, names the tool/rules
   applied, and asserts no logic changes.
6. Update the Linear ticket: link PR, move to **In Review**.
7. Skip `/ce-compound` — unless the sweep motivated a new lint rule or formatter
   config, in which case document that decision.

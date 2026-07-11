# CI Workflow

**Branch:** `ci/<ticket-id>-<short-slug>`
**Use when:** the ticket changes CI pipelines — GitHub Actions workflows, test
matrices, caching, required checks, pipeline speed.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`); understand the pain: broken
   pipeline, slow pipeline, missing check, or new automation.
2. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

- **`gh` CLI** — essential: `gh run list/view/watch` to inspect and monitor runs.
- **Context7 / docs researchers** — action versions, runner images, syntax for
  unfamiliar CI features.
- **Railway / Vercel MCP** — if the pipeline deploys there.

## Phase 2 — Plan & change

1. `/ce-plan` — lightweight: current pipeline behavior → target behavior → the
   YAML/config changes to get there. For a *broken* pipeline, `/ce-debug` first:
   read the failing run logs (`gh run view --log-failed`) and root-cause before editing.
2. On `ci/<ticket-id>-<slug>`, make the change. Pin action versions; never put
   secrets in workflow files (use repository/environment secrets).

## Phase 3 — Verify on real runs

3. CI changes can only be trusted by running them: push the branch and watch the
   actual run (`gh run watch`). Iterate until green — local YAML linting is not
   verification.
4. Confirm both directions where relevant: the check passes on good code *and*
   fails on bad code (a check that can't fail protects nothing).

## Phase 4 — Ship & close

5. `/ce-code-review` — quick pass focused on security (untrusted input in `run:`
   steps, permissions blocks, secret exposure).
6. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>` and links the green
   run that proves the pipeline works.
7. Update the Linear ticket: link PR + run URL, move to **In Review**.
8. `/ce-compound` — CI gotchas are prime learnings; document runner quirks, cache
   behaviors, and timing cliffs you hit.

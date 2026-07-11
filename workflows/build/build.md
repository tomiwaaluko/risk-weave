# Build Workflow

**Branch:** `build/<ticket-id>-<short-slug>`
**Use when:** the ticket changes the build system or packaging — Dockerfiles,
docker-compose, bundlers, package manifests' build config, compilation targets.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`); move to **In Progress**.
2. `docs/solutions/` check — build-system fixes are frequently repeats.

## Phase 1 — Tool & MCP survey

- **Context7 / docs researchers** — bundler/Docker/toolchain documentation.
- **Railway / Vercel MCP** — if the build feeds a deploy there (build logs,
  image behavior in the real environment).
- **`gh` CLI** — CI build results across the matrix.

## Phase 2 — Change

1. `/ce-plan` — lightweight: state the current build behavior, the target, and how
   you'll prove the change works from a **clean environment**.
2. On `build/<ticket-id>-<slug>`, make the change. Pin tool and image versions;
   keep build config boring and explicit over clever.

## Phase 3 — Verify from clean

3. The only proof for build changes is a clean build: wipe caches/artifacts
   (`docker build --no-cache`, fresh install of deps) and build from scratch.
4. Run the built artifact, not just the build: boot the container/app and exercise
   one real flow. Compare artifact size/build time before vs. after if relevant.

## Phase 4 — Ship & close

5. `/ce-code-review` — pass focused on reproducibility (unpinned versions, host
   leakage into images, secrets baked into layers).
6. `/ce-commit-push-pr` — PR body cites `Closes <TICKET-ID>` and documents the
   clean-build verification performed.
7. Update the Linear ticket: link PR, move to **In Review**.
8. `/ce-compound` — document build gotchas (cache invalidation traps, image quirks).

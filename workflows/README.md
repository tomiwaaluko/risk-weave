# Workflows

Tool-agnostic workflow definitions for AI agents (Claude Code, Cursor, Codex, etc.).
Each subfolder maps to a git branch naming convention. When an agent picks up a
Linear ticket, it selects the workflow matching the branch type, then follows the
markdown file step by step. Each step that starts with a `/ce-*` slash command
invokes the corresponding skill from the
[compound-engineering plugin](https://github.com/everyinc/compound-engineering-plugin).

## Shared lifecycle (applies to every workflow)

Every workflow follows the same outer shell:

1. **Ticket intake** — fetch the Linear ticket via the Linear MCP, read the full
   description/comments/links, move it to **In Progress**.
2. **Tool & MCP survey** — decide which MCPs/plugins the ticket needs (see catalog
   below) and load only those.
3. **Branch** — create `<type>/<ticket-id>-<short-slug>` from `main`
   (e.g., `feature/RIS-12-severity-slider`).
4. **The workflow body** — the skill chain defined in the type's markdown file.
5. **Ship & close** — open a PR with `/ce-commit-push-pr` (body cites the ticket ID
   with `Closes <TICKET-ID>` and any spec requirement IDs), link the PR on the
   Linear ticket, comment a summary, and move the ticket to **In Review**
   (or **Done** if auto-merge applies).
6. **Compound** — run `/ce-compound` to capture learnings into `docs/solutions/`
   so the next cycle starts smarter.

## MCP / plugin catalog

During the tool survey, pick from this catalog based on what the ticket touches:

| MCP / plugin | Use when the ticket involves |
|---|---|
| **Linear** | Always — ticket read, status updates, comments, PR links |
| **git + `gh` CLI** | Always — branching, commits, PRs, CI status |
| **claude-mem / `mem-search`** | Always at start — recall past sessions and prior solutions |
| **compound-engineering learnings** (`docs/solutions/`) | Always at start — check documented past learnings |
| **Context7 / docs researchers** | Unfamiliar libraries or framework APIs |
| **Supabase MCP** | Database schema, migrations, SQL, edge functions |
| **Railway MCP** | Deployments, infra, environment variables, service logs |
| **Vercel MCP** | Frontend deployments, preview builds, runtime logs |
| **Figma MCP** | UI work with an existing design, or pushing designs back to Figma |
| **claude-in-chrome** | Browser verification of UI changes, console/network debugging |
| **Codex plugin** (`codex:rescue`) | Second implementation/diagnosis pass when stuck |
| **Notion / Google Drive MCP** | Ticket references external docs |

Rule of thumb: load the minimum set at the start, and re-survey mid-workflow if
the ticket turns out to touch a system you didn't anticipate.

## Workflow index

| Branch type | Purpose | Weight |
|---|---|---|
| [feature](feature/feature.md) | New user-facing capability | Full loop |
| [fix](fix/fix.md) | Small correction (not a reproducible defect) | Light |
| [bugfix](bugfix/bugfix.md) | Reproducible defect, root-cause driven | Medium |
| [hotfix](hotfix/hotfix.md) | Urgent production-breaking issue | Expedited |
| [refactor](refactor/refactor.md) | Restructure code without behavior change | Medium |
| [perf](perf/perf.md) | Performance improvement | Medium |
| [release](release/release.md) | Version cut, changelog, release prep | Medium |
| [chore](chore/chore.md) | Maintenance, deps, housekeeping | Light |
| [docs](docs/docs.md) | Documentation only | Light |
| [test](test/test.md) | Test coverage only | Light |
| [style](style/style.md) | Formatting/lint only, no logic change | Minimal |
| [ci](ci/ci.md) | CI pipeline changes | Light |
| [build](build/build.md) | Build system / packaging changes | Light |
| [experiment](experiment/experiment.md) | Exploratory build, learnings are the deliverable | Exploratory |
| [spike](spike/spike.md) | Time-boxed research, findings doc is the deliverable | Exploratory |
| [revert](revert/revert.md) | Back out a bad change | Minimal |

# Skills

Vendored copies of the [compound-engineering plugin](https://github.com/everyinc/compound-engineering-plugin)
skills referenced by the `workflows/` files, so that **every** AI tool working in
this repo (Cursor, Codex, Claude Code, etc.) can read them — not just Claude Code
with the plugin installed.

Each skill is a folder containing `SKILL.md` (the entry point — frontmatter with
name/description, then the instructions) plus a `references/` directory the
SKILL.md may point into.

## How to use

- **Claude Code with the plugin installed:** ignore this folder — invoke the real
  skill (`/ce-plan`, `/ce-work`, …) via the Skill tool. The plugin version is the
  source of truth at runtime and may be newer.
- **Any other tool (Cursor, Codex, plugin-less Claude Code):** when a workflow
  step says `/ce-<name>`, open `skills/ce-<name>/SKILL.md` and follow it as the
  instruction set for that step.

## Vendored skills (from plugin v3.13.0)

| Skill | Used by workflows for |
|---|---|
| `ce-brainstorm` | Requirements exploration (feature, experiment, spike) |
| `ce-plan` | Implementation-ready plans (feature, refactor, test, ci, build) |
| `ce-doc-review` | Persona review of plans/docs (feature, docs, spike, refactor) |
| `ce-worktree` | Isolated worktrees (feature, refactor, experiment) |
| `ce-work` | Plan execution with task tracking |
| `ce-simplify-code` | Pre-review simplification pass |
| `ce-code-review` | Multi-agent review before PR |
| `ce-debug` | Root-cause debugging (bugfix, hotfix, test, ci) |
| `ce-optimize` | Performance work (perf) |
| `ce-ideate` | Idea generation/ranking (experiment) |
| `ce-demo-reel` | Visual proof for PRs (feature) |
| `ce-commit-push-pr` | Commit, push, PR with value-first description (all) |
| `ce-compound` | Capture learnings into docs/solutions/ (all) |

## Updating

These are snapshots, not a submodule. To refresh after a plugin update, re-copy from
the plugin cache (adjust the version segment):

```
cp -r ~/.claude/plugins/cache/compound-engineering-plugin/compound-engineering/<version>/skills/<skill-name> skills/
```

Note: some SKILL.md files dispatch to plugin agents (e.g. `compound-engineering:ce-correctness-reviewer`).
Those agent definitions live in the plugin, not in this folder — tools without the
plugin should treat such steps as "apply this persona's checklist yourself" using
the persona descriptions inside the skill's `references/`.

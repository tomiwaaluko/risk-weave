# Spike Workflow

**Branch:** `spike/<ticket-id>-<short-slug>`
**Use when:** the ticket is time-boxed *research* to answer a question — evaluate a
library, assess feasibility, compare approaches. Unlike an **experiment** (which
builds to learn), a spike primarily reads, probes, and writes: **the findings
document is the deliverable.**

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`). Extract the research question
   and the time box. Rewrite the question as something answerable
   ("Can React Flow render 200 nodes with live re-weighting at 60fps?" not
   "look into React Flow").
2. `mem-search` + `docs/solutions/` — the question may already be answered.
3. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

Research-heavy — this phase matters most here:

- **Web research / `ce-web-researcher`** — prior art, benchmarks, community verdicts.
- **Context7 / docs researchers** — official docs for candidate libraries.
- **claude-in-chrome** — probing live demos/playgrounds of candidate tools.
- **Codex plugin** — a second model's read on a gnarly feasibility question.

## Phase 2 — Frame the investigation

1. `/ce-brainstorm` — decompose the question into sub-questions and decide the
   evidence each needs (docs read? micro-benchmark? throwaway prototype?).

## Phase 3 — Investigate (respect the time box)

2. Work through the sub-questions. Any code written is throwaway probe code on
   `spike/<ticket-id>-<slug>` — no production standards apply, and it must not
   be merged. When the time box expires, write up what you have; "unresolved,
   here's what it would take" is a valid finding.

## Phase 4 — Write the findings

3. Write a findings document (e.g., `docs/spikes/<ticket-id>-<slug>.md`): the
   question, what was evaluated, evidence gathered, answer/recommendation, and
   risks/unknowns that remain. Recommendations must trace to evidence, not vibes.
4. `/ce-doc-review` — persona review of the findings doc if a real decision
   (architecture, dependency adoption) hangs on it.

## Phase 5 — Ship & close

5. `/ce-commit-push-pr` — PR contains **only the findings document** (probe code
   stays on the branch, linked for reference). Body cites `Closes <TICKET-ID>`
   and the one-line answer.
6. Update the Linear ticket: paste the answer/recommendation as a comment, link
   the PR and branch, move to **Done**. Create follow-up tickets for the decided
   next steps (ADR, feature, another spike) and link them.
7. `/ce-compound` — fold the answer into `docs/solutions/` so nobody re-researches it.

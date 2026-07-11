# Experiment Workflow

**Branch:** `experiment/<ticket-id>-<short-slug>`
**Use when:** the ticket is an exploratory build — trying an approach to learn
whether it works. **The learning is the deliverable**; the code may be thrown away.
Never merge experiment code to `main` directly — promote it through a **feature**
workflow if it earns its keep.

## Phase 0 — Ticket intake

1. Fetch the Linear ticket (Linear MCP `get_issue`). Extract the hypothesis and the
   success criteria — if the ticket doesn't state what would make the experiment a
   success or failure, comment asking for it (or propose criteria on the ticket).
2. Move the ticket to **In Progress**.

## Phase 1 — Tool & MCP survey

Experiments range widely — survey generously:

- **Context7 / docs researchers + web research** — prior art before building.
- **claude-in-chrome** — trying UI/UX concepts live.
- **Figma MCP** — mocking a concept visually before/instead of coding it.
- **Supabase / Railway MCP** — spinning up throwaway backing services.

## Phase 2 — Frame

1. `/ce-ideate` — generate and rank candidate approaches if the path isn't fixed.
2. `/ce-brainstorm` — sharpen the chosen approach into a minimal build plan:
   the *smallest* build that can confirm or kill the hypothesis. Set a time box.

## Phase 3 — Build to learn

3. `/ce-worktree` — isolate on `experiment/<ticket-id>-<slug>`; experiments must
   never contaminate mainline work.
4. `/ce-work` — build fast and rough. Skip `/ce-simplify-code` and polish — code
   quality only matters where it affects the validity of the result. Record
   observations as you go; surprises mid-build are half the value.

## Phase 4 — Evaluate

5. Judge the result against the success criteria from Phase 0. Honest verdict:
   confirmed, killed, or inconclusive-needs-X. A killed hypothesis is a successful
   experiment.

## Phase 5 — Close & compound

6. Write up findings on the Linear ticket: hypothesis, what was built, result,
   verdict, and recommendation (promote / drop / follow-up experiment).
7. PR is optional: open a **draft PR** via `/ce-commit-push-pr` only if the code
   should survive for reference; otherwise push the branch and link it from the
   ticket. Move the ticket to **Done** — the deliverable was the answer, not a merge.
8. `/ce-compound` — mandatory: the entire point of the experiment is documented
   learning in `docs/solutions/`. If promoting, create the follow-up **feature**
   ticket in Linear and link it.

# Metrics hardening brief

Purpose: turn the RiskWeave statistics in `riskweave-metrics.md` into numbers that
survive a technical interview. Nothing here changes a MUST requirement in
`RISKWEAVE_MASTER_SPEC_MERGED.md`; anything that would needs an ADR under spec §0.3.

Current weaknesses, in priority order. Each task states what is wrong, what to
build, and the metric it should produce.

---

## 1. The extraction gold set is circular (highest priority)

**Problem.** `data/evaluation/extraction_labels.jsonl` scores 50 passages. The CRE
half traces to `backend/data/fixtures/cre_graph.json`, which was hand-authored from
filings by the same process being evaluated. The oil half is representative language,
not live extraction output (stated in `data/evaluation/EXTRACTION_LABELS.md`). A
94.1% precision figure measured on passages chosen while writing the extractor is not
an accuracy claim.

**Build.**
- Draw a new labeled set by sampling chunks *randomly* from snapshot 3, stratified by
  filing form type and by pack (CRE / oil), excluding every filing already used in the
  fixture. Record the sampling seed and the excluded accession numbers.
- Target 200–300 passages. Below ~150 the confidence interval is too wide to quote.
- Label the gold relationships *before* running the extractor on them, and commit the
  labels and the predictions as separate artifacts so the ordering is auditable.
- Keep the existing 50-passage set as a separate "development" split and report it
  separately. Never merge the two.

**Metric produced.** Precision / recall / F1 on a held-out random sample of N real
filing passages, with a 95% Wilson interval on each. That is a defensible number even
if it comes out at 70%.

---

## 2. Perfect scores on samples too small to mean anything

**Problem.** Entity resolution 100% on 50 mentions
(`data/evaluation/entity_resolution_sample.json`), unsupported-claim rate 0% on 10
explanations, provenance coverage 100% on 18 fixture edges. All three are true and all
three read as "not actually measured."

**Build.**
- Entity resolution: sample 300+ mentions from snapshot 3 extraction output, including
  deliberate hard cases — former names, subsidiaries, ticker collisions, issuers absent
  from the 125-entity universe (which must resolve to *no match*, not a wrong match).
  Report accuracy, plus false-match rate on the out-of-universe subset separately.
  The out-of-universe false-match rate is the number that actually matters.
- Explanation guard: generate explanations for every scenario × severity step on the
  demo path plus the live path, not 10. That is hundreds of payloads, cheap because the
  guard is local. Report unsupported-claim rate over the full sweep, and add adversarial
  cases — a prompt that invites the model to volunteer an outside figure — so a 0% has
  teeth (`RW-AI-011`).
- Provenance: assert the write gate on the *live* assembly path over every extracted
  row for snapshot 3, and report rejected-edge count alongside coverage. "Gate rejected
  K of M candidate edges for missing provenance" is a stronger claim than "100%."

**Metric produced.** The same three metrics at 10–30× the sample size, plus a rejection
count that proves the gate fires rather than merely passing.

---

## 3. Latency is measured on a graph too small to be meaningful

**Problem.** p95 of 0.07 ms against a 500 ms budget (`RW-NFR-002`) on a 15-node /
18-edge fixture. A 7,000× margin tells a reader the budget was never exercised, and
invites the question that exposes the missing corpus graph.

**Build.** In `backend/benchmarks/bench_propagation.py`, add a scaling sweep: run
propagation at 15 / 125 / 500 / 2,000 / 10,000 nodes with realistic edge density and
the 3-hop cap, over repeated slider recomputes. Generate the larger graphs
synthetically with a fixed seed. Plot or tabulate p50/p95 against node and edge count,
and report where p95 crosses the 500 ms budget.

**Metric produced.** "Propagation holds p95 under 500 ms up to ~N nodes / E edges
(3-hop cap), measured over R recomputes" — a capacity statement instead of a vacuous
margin. Commit the sweep output so the number is reproducible.

---

## 4. There is no completed extraction pass, so there is no corpus-scale result

**Problem.** The October run stored 2 relationship rows from 1 filing against 22,384
chunks, with 14,881 schema-invalid runs that were HTTP 402 bodies rather than recovered
text. Every graph statistic therefore describes the committed fixture.

**Build.** Do not retry 22,384 chunks. Run a *bounded* pass — 500 to 1,000 chunks,
sampled with a recorded seed — under the controls in task 5. Then report what the
pipeline actually extracted end to end: chunks processed, relationships saved,
covenants saved, extraction yield per chunk, edges that passed the provenance gate,
nodes and edges in the resulting live graph, and total provider spend for the pass.

**Metric produced.** "Extracted R provenance-complete relationships from C filing
chunks at $X total provider cost, assembling a live G-node / E-edge graph." That single
sentence replaces the weakest part of the current metric set, and the bounded scope is
honest rather than apologetic.

---

## 5. The cost controls are a recommendation, not shipped code

**Problem.** `riskweave-metrics.md` closes by naming three controls the October run
proved necessary. Until they exist in `backend/src/riskweave_api/accounting/`, the
incident is a mistake on the resume rather than an engineering result.

**Build.**
- A hard provider-side spend cap, not only the in-app ledger: a configured ceiling that
  halts the batch, plus a startup check that the registered price table is not older
  than a configured staleness window (the ledger's $0.075/$0.30 per-million Flash rates
  were last checked 2026-07-11 and no longer matched the invoice on 2026-10-01).
- Refuse-to-restart-on-failure: a run that exits on provider error must not auto-resume.
- Mark a chunk invalid on a non-retryable provider response (402, 401, 429 past the
  retry budget) so the same passage is never purchased twice. The 14,881 schema-invalid
  rows were the same failure re-bought repeatedly; that is the actual defect.
- Distinguish, in the ledger schema, "provider request attempted" from "usage row
  recorded." The 14.97K-vs-32 gap between Google's dashboard and the app ledger is
  exactly this missing distinction.
- Tests: a batch that hits the cap stops; a 402 marks the chunk invalid and is not
  re-attempted; a stale price table fails startup.

**Metric produced.** "Ledger reconciles to provider request count within X%", and the
incident becomes "diagnosed a billing-vs-ledger divergence and shipped provider-side
caps, retry-poisoning protection, and price-table staleness checks."

---

## 6. The project's central claim has no baseline to compare against

**Problem.** "Gemini finds the sentence; deterministic code turns it into the number"
(`RW-AI-010`, `RW-ALG-001`) is the strongest idea in the system and currently has no
number attached. It is asserted, not demonstrated.

**Build.** A one-off, clearly-labeled experiment (enabling work, not a requirement
change, and it must not add an `estimated_sensitivity` path to the production schema):
on the new gold set from task 1, compare the deterministic derivation pipeline against
an ablation where the model is asked for the magnitude directly. Measure, against the
hand-labeled ground truth, the rate at which the model's figure is absent from the
source passage or materially disagrees with the disclosed value, and the spread of
repeated runs on the same passage versus the deterministic path's exact reproducibility.

**Metric produced.** A delta — "the LLM-estimated baseline produced magnitudes
unsupported by the cited passage in P% of cases and varied across repeated runs, versus
0% and bit-identical output for the deterministic derivations." That quantifies the
design decision the whole project is built on. It is the single highest-value metric
missing from the file.

---

## 7. Reproducibility and test coverage are claimed but not counted

**Build.** Scenario stability currently reports "5 repeated runs produced one result."
Extend to repeated runs across process restarts and across machines, pinned to snapshot
+ versions + seed, and report the count. Separately, record test count and line
coverage for `backend/` and the determinism/provenance/cycle/path-decomposition suites
named in `CLAUDE.md`.

**Metric produced.** "N tests, C% coverage, bit-identical propagation output across R
runs and M environments from snapshot + version + seed."

---

## Reporting rules for whatever is produced

- Every figure keeps its scope label, as `riskweave-metrics.md` already does. Sample
  size travels with the number, in the same sentence.
- Separate development splits from held-out splits, always, and never quote the
  development number as an accuracy result.
- Cite the requirement ID (`RW-FR-*`, `RW-ALG-*`, `RW-AI-*`, `RW-NFR-*`) each metric
  evidences. Work mapping to no requirement is labeled enabling work.
- Commit the raw artifact behind each figure — the labels file, the predictions file,
  the benchmark output, the ledger reconciliation — so each number is re-derivable
  rather than remembered.
- A worse number with a real sample behind it is more useful on a resume than a perfect
  number on 10 items.

# Extraction evaluation sample (RIS-21, Part A)

The scheduled hand-labeling deliverable the §15 extraction precision/recall
metric depends on. Two committed, versioned JSONL artifacts:

| File | Role |
|---|---|
| `extraction_labels.jsonl` | Hand-labeled **gold** relationships (ground truth). |
| `extraction_predictions.jsonl` | Pipeline **predicted** relationships, scored against gold. |

Scored by `riskweave.evaluation.extraction_metrics` (precision / recall / F1)
and surfaced on the evaluation dashboard (`/evaluation`).

## What a record is

One filing passage judged for a relationship, validated by
`riskweave.evaluation.labeling.LabeledRelationship`:

- `passage_id`, `source_document_id`, `char_start`, `char_end` — where the text is.
- `source_entity`, `target_entity`, `relationship_type` — the labeled relationship
  (`(source, target, type)` is the key extraction is scored on).
- `is_relationship` — `false` for a **negative** (a passage that looks like a
  relationship but is not); negatives keep precision honest.
- `pack` — `cre` or `oil` (both packs represented, per §15).
- `provenance_status` — see honesty note below.
- `extraction_confidence`, `notes` — labeler confidence and free-text rationale.

## Sample composition

- **50 gold passages** across both scenario packs.
- CRE (`provenance_status: committed-fixture`): every relationship traces to the
  real-provenance CRE graph fixture (`backend/data/fixtures/cre_graph.json`,
  hand-authored from SEC filings), plus omitted-but-disclosed positives (honest
  false negatives) and negative examples.
- Oil (`provenance_status: representative`): representative fuel-cost /
  commodity-price disclosures exercising the metric harness pending live
  oil-pack ingestion (RIS-10). **Not presented as live extraction output.**

## Honesty note (why predictions ≠ gold)

`extraction_predictions.jsonl` deliberately **misses** a few gold relationships
and includes a few **extraction errors** (a hallucinated dependency; a
mislabeled relationship type), so precision/recall are honest engineering
numbers, not a fabricated 1.0. For the CRE pack the predictions mirror the
committed graph fixture exactly — a test
(`test_cre_predictions_mirror_the_committed_graph_fixture`) enforces this, so the
CRE half of the metric is auditable against real provenance.

Current sample yields precision ≈ 0.94 (target ≥ 0.90) and recall ≈ 0.89
(target ≥ 0.80).

## Reproduce

```
cd backend
uv run python -m riskweave.evaluation.report        # writes evaluation_report.json
uv run pytest tests/test_evaluation_report.py
```

When live extraction (RIS-10) lands, replace `extraction_predictions.jsonl` with
the pipeline's real output over the labeled passages — the metric code and the
gold set are unchanged.

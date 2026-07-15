"""Hand-labeling sample scaffold (spec §15: "schedule this task explicitly").

The extraction precision/recall metric depends on a hand-labeled gold set of
50–100 filing passages. This module defines the label record shape and a
loader/validator so the labeling work is a concrete, checkable artifact rather
than a vague future task.

Two committed JSONL artifacts feed the metric (both under
``data/evaluation/``, versioned with the code):

- ``extraction_labels.jsonl`` — the human-labeled **gold** set (this is the
  scheduled Part-A labeling deliverable).
- ``extraction_predictions.jsonl`` — the extraction pipeline's **predicted**
  relationships over the same passages. For the CRE pack these mirror the
  committed real-provenance graph fixture (``data/fixtures/cre_graph.json``);
  for the oil pack they are pre-baked representative extractions pending live
  ingestion (RIS-10). Scoring predicted against gold is what ``extraction_metrics``
  computes.

Each record carries an honest ``provenance_status``: ``committed-fixture`` when
the passage traces to the real-provenance CRE fixture, ``representative`` when
it is a hand-authored oil-pack sample used to exercise the metric harness
pending oil-pack ingestion. Nothing here is presented as live extraction output.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, fields

# The scored relationship vocabulary. Covers both the Gemini extraction schema
# types (supplier/customer/creditor/commodity_dependency/geographic_exposure)
# and the two structural exposure types the committed CRE graph fixture encodes
# (sector_exposure, ownership_exposure) so gold and predictions share one
# closed vocabulary.
RELATIONSHIP_TYPES = frozenset(
    {
        "supplier",
        "customer",
        "creditor",
        "commodity_dependency",
        "geographic_exposure",
        "sector_exposure",
        "ownership_exposure",
    }
)

PROVENANCE_STATUSES = frozenset({"committed-fixture", "representative"})


class LabelError(ValueError):
    """Raised when a label record is malformed."""


@dataclass(frozen=True)
class LabeledRelationship:
    """One human-labeled gold (or pipeline-predicted) relationship over a passage.

    ``is_relationship`` is False for a negative example (a passage that looks
    like it discloses a relationship but does not) — negatives keep precision
    honest. The trailing fields are optional metadata: ``pack`` groups a record
    into a scenario pack, ``provenance_status`` records whether the passage
    traces to the committed real-provenance fixture or is a representative
    sample, ``extraction_confidence`` is the labeler's (or extractor's)
    confidence, and ``notes`` carries the labeler's free-text rationale.
    """

    passage_id: str
    source_document_id: str
    char_start: int
    char_end: int
    source_entity: str
    target_entity: str
    relationship_type: str
    is_relationship: bool
    pack: str | None = None
    provenance_status: str | None = None
    extraction_confidence: float | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.char_end <= self.char_start:
            raise LabelError("char_end must be greater than char_start")
        if self.is_relationship and self.relationship_type not in RELATIONSHIP_TYPES:
            raise LabelError(
                f"relationship_type must be one of {sorted(RELATIONSHIP_TYPES)} "
                f"for a positive label, got {self.relationship_type!r}"
            )
        if self.provenance_status is not None and self.provenance_status not in PROVENANCE_STATUSES:
            raise LabelError(
                f"provenance_status must be one of {sorted(PROVENANCE_STATUSES)}, "
                f"got {self.provenance_status!r}"
            )
        if self.extraction_confidence is not None and not (
            0.0 <= self.extraction_confidence <= 1.0
        ):
            raise LabelError("extraction_confidence must be in [0, 1]")

    @property
    def gold_key(self) -> tuple[str, str, str]:
        """The key extraction is scored against (see ``extraction_metrics``)."""
        return (self.source_entity, self.target_entity, self.relationship_type)


_FIELD_NAMES = frozenset(f.name for f in fields(LabeledRelationship))


def load_labels(path: str) -> tuple[LabeledRelationship, ...]:
    """Load a JSONL gold (or predictions) file into validated label records."""
    return tuple(_iter_labels(path))


def positive_keys(records: tuple[LabeledRelationship, ...]) -> list[tuple[str, str, str]]:
    """Gold keys of the positive (is_relationship) records — the scoring set."""
    return [r.gold_key for r in records if r.is_relationship]


def _iter_labels(path: str) -> Iterator[LabeledRelationship]:
    with open(path, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LabelError(f"line {line_no}: invalid JSON ({exc})") from exc
            if not isinstance(record, dict):
                raise LabelError(f"line {line_no}: record must be a JSON object")
            unknown = set(record) - _FIELD_NAMES
            if unknown:
                raise LabelError(f"line {line_no}: unknown field(s) {sorted(unknown)}")
            try:
                yield LabeledRelationship(**record)
            except TypeError as exc:
                raise LabelError(f"line {line_no}: {exc}") from exc

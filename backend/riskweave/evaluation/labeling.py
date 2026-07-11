"""Hand-labeling sample scaffold (spec §15: "schedule this task explicitly").

The extraction precision/recall metric depends on a hand-labeled gold set of
50–100 filing passages. This module defines the label record shape and a
loader/validator so the labeling work is a concrete, checkable artifact rather
than a vague future task. The labeled JSONL file itself is produced by a human
reviewer over real filings (RIS-8/RIS-10 output) and is not fabricated here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

RELATIONSHIP_TYPES = frozenset(
    {
        "supplier",
        "customer",
        "creditor",
        "commodity_dependency",
        "geographic_exposure",
    }
)


class LabelError(ValueError):
    """Raised when a label record is malformed."""


@dataclass(frozen=True)
class LabeledRelationship:
    """One human-labeled gold relationship over a filing passage.

    ``is_relationship`` is False for a negative example (a passage that looks
    like it discloses a relationship but does not) — negatives keep precision
    honest.
    """

    passage_id: str
    source_document_id: str
    char_start: int
    char_end: int
    source_entity: str
    target_entity: str
    relationship_type: str
    is_relationship: bool

    def __post_init__(self) -> None:
        if self.char_end <= self.char_start:
            raise LabelError("char_end must be greater than char_start")
        if self.is_relationship and self.relationship_type not in RELATIONSHIP_TYPES:
            raise LabelError(
                f"relationship_type must be one of {sorted(RELATIONSHIP_TYPES)} "
                f"for a positive label, got {self.relationship_type!r}"
            )

    @property
    def gold_key(self) -> tuple[str, str, str]:
        """The key extraction is scored against (see ``extraction_metrics``)."""
        return (self.source_entity, self.target_entity, self.relationship_type)


def load_labels(path: str) -> tuple[LabeledRelationship, ...]:
    """Load a JSONL gold file into validated label records."""
    return tuple(_iter_labels(path))


def _iter_labels(path: str) -> Iterator[LabeledRelationship]:
    with open(path, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LabelError(f"line {line_no}: invalid JSON ({exc})") from exc
            try:
                yield LabeledRelationship(**record)
            except TypeError as exc:
                raise LabelError(f"line {line_no}: {exc}") from exc

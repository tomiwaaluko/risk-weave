"""Provenance and weight-record types.

Enforces the project's defining invariant (CLAUDE.md, spec `RW-ALG-004`,
`RW-ALG-032`): **no edge weight may exist without complete provenance.** The
type system makes an under-provenanced weight *unconstructible* — every
``WeightRecord`` requires a fully-validated ``Provenance`` with no default, and
both dataclasses validate themselves at construction time.

These types are pure data: no database, no network, no clock. Callers pass in
already-fetched values and the passage they were read from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Mapping


class ProvenanceError(ValueError):
    """Raised when a weight is constructed without complete, valid provenance."""


@dataclass(frozen=True)
class Provenance:
    """Evidence backing a single derived number.

    Every field is mandatory. Construction fails loudly if any is missing or
    implausible, so a ``Provenance`` instance is proof that the evidence exists.

    Attributes
    ----------
    source_document_id:
        Stable id of the source filing/dataset (e.g. an EDGAR accession number
        or a FRED series id).
    filing_date:
        Publication/filing date of the source document.
    source_passage:
        The exact quoted span the value was read from. Verbatim — not a summary.
    char_start, char_end:
        Character offsets of ``source_passage`` within the source document, so
        the evidence panel can highlight it (`RW-ALG-032`). Half-open
        ``[char_start, char_end)``; the length MUST match ``source_passage``.
    data_timestamp:
        Timestamp of the market/economic input used (`RW-ALG-032`). For a
        static disclosure this is the filing datetime; for market series it is
        the as-of of the data window.
    extraction_confidence:
        Extraction / data-quality confidence in ``[0, 1]``. Per `RW-ALG-007`
        this is a data-quality signal, **not** a statistical guarantee, and the
        UI must label it as such.
    """

    source_document_id: str
    filing_date: date
    source_passage: str
    char_start: int
    char_end: int
    data_timestamp: datetime
    extraction_confidence: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_document_id, str) or not self.source_document_id.strip():
            raise ProvenanceError("source_document_id must be a non-empty string")
        if not isinstance(self.filing_date, date):
            raise ProvenanceError("filing_date must be a datetime.date")
        if not isinstance(self.source_passage, str) or not self.source_passage.strip():
            raise ProvenanceError("source_passage must be a non-empty quoted span")
        if not isinstance(self.char_start, int) or not isinstance(self.char_end, int):
            raise ProvenanceError("character offsets must be integers")
        if self.char_start < 0 or self.char_end < 0:
            raise ProvenanceError("character offsets must be non-negative")
        if self.char_end <= self.char_start:
            raise ProvenanceError("char_end must be greater than char_start")
        if self.char_end - self.char_start != len(self.source_passage):
            raise ProvenanceError(
                "offset span "
                f"({self.char_end - self.char_start}) does not match passage "
                f"length ({len(self.source_passage)})"
            )
        if not isinstance(self.data_timestamp, datetime):
            raise ProvenanceError("data_timestamp must be a datetime.datetime")
        conf = self.extraction_confidence
        if not isinstance(conf, (int, float)) or isinstance(conf, bool):
            raise ProvenanceError("extraction_confidence must be a real number")
        if math.isnan(conf) or not (0.0 <= conf <= 1.0):
            raise ProvenanceError("extraction_confidence must be within [0, 1]")


@dataclass(frozen=True)
class WeightRecord:
    """A derived edge weight bound to its method and its evidence.

    There is no way to construct a ``WeightRecord`` without passing a valid
    ``Provenance`` (no default is provided and the value is type-checked), which
    is how the "no edge without provenance" invariant is enforced structurally
    rather than by convention.

    Attributes
    ----------
    value:
        The derived scalar. Semantics depend on the method (a share in ``[0, 1]``
        for cost/segment/geo/credit methods; an OLS beta for the regression
        methods, which may be negative).
    method_id:
        Registered `DER-*` method id (spec §12.1).
    method_version:
        Version string of the derivation method used, for reproducibility.
    inputs:
        The concrete input references actually consumed, for audit. Stored as a
        read-only mapping.
    provenance:
        The evidence backing ``value``. Mandatory.
    data_timestamps:
        Timestamps of every market/economic input feeding the computation.
    """

    value: float
    method_id: str
    method_version: str
    inputs: Mapping[str, float]
    provenance: Provenance
    data_timestamps: tuple[datetime, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, Provenance):
            raise ProvenanceError(
                "WeightRecord requires a validated Provenance; a weight without "
                "provenance is unconstructible"
            )
        if not isinstance(self.method_id, str) or not self.method_id.strip():
            raise ProvenanceError("method_id must be a non-empty string")
        if not isinstance(self.method_version, str) or not self.method_version.strip():
            raise ProvenanceError("method_version must be a non-empty string")
        val = self.value
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise ProvenanceError("value must be a real number")
        if math.isnan(val) or math.isinf(val):
            raise ProvenanceError("value must be finite")
        if not isinstance(self.data_timestamps, tuple) or not self.data_timestamps:
            raise ProvenanceError("data_timestamps must be a non-empty tuple")
        if not all(isinstance(ts, datetime) for ts in self.data_timestamps):
            raise ProvenanceError("every data_timestamp must be a datetime.datetime")
        # Freeze the inputs mapping so a stored record cannot be mutated post-hoc.
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))

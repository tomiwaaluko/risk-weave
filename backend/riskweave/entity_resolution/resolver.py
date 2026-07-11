from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ENTITY_RESOLUTION_CONFIDENCE_THRESHOLD = 0.80

_PUNCTUATION_RE = re.compile(r"[^a-z0-9]+")
_LEGAL_SUFFIXES = {
    "association",
    "bancorp",
    "company",
    "co",
    "corp",
    "corporation",
    "de",
    "inc",
    "incorporated",
    "llc",
    "lp",
    "ltd",
    "na",
    "new",
    "plc",
    "the",
}
_TOKEN_ABBREVIATIONS = {
    "intl": "international",
    "natl": "national",
    "svcs": "services",
    "svc": "services",
    "finl": "financial",
    "fin": "financial",
    "grp": "group",
    "cos": "companies",
}


def normalize_identifier(value: str | int | None) -> str:
    """Normalize CIK/ticker/LEI-like identifiers for exact deterministic lookup."""
    if value is None:
        return ""
    text = str(value).strip().upper()
    if text.isdigit():
        return text.zfill(10)
    return re.sub(r"[^A-Z0-9]", "", text)


def normalize_name(value: str) -> str:
    """Normalize issuer names without weakening identifier-first matching."""
    text = value.casefold().replace("&", " and ")
    tokens = []
    for token in _PUNCTUATION_RE.sub(" ", text).split():
        expanded = _TOKEN_ABBREVIATIONS.get(token, token)
        if expanded not in _LEGAL_SUFFIXES:
            tokens.append(expanded)
    return " ".join(tokens)


@dataclass(frozen=True)
class EntityRecord:
    id: str
    canonical_name: str
    entity_type: str
    aliases: tuple[str, ...] = ()
    ticker: str | None = None
    cik: str | None = None
    lei: str | None = None
    fred_series_ids: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: dict) -> EntityRecord:
        return cls(
            id=raw["id"],
            canonical_name=raw["canonical_name"],
            entity_type=raw["entity_type"],
            aliases=tuple(raw.get("aliases") or ()),
            ticker=raw.get("ticker"),
            cik=raw.get("cik"),
            lei=raw.get("lei"),
            fred_series_ids=tuple(raw.get("fred_series_ids") or ()),
        )


@dataclass(frozen=True)
class AuditEvent:
    input_string: str
    matched_entity_id: str
    layer: Literal["deterministic", "gemini_residual", "manual_correction"]
    confidence: float
    timestamp: str
    matched_field: str
    rationale: str = ""


@dataclass(frozen=True)
class UnresolvedMention:
    input_string: str
    reason: Literal[
        "no_match",
        "ambiguous_deterministic_match",
        "proposal_below_threshold",
        "proposal_unknown_entity",
        "proposal_for_already_resolved",
    ]
    candidates: tuple[str, ...] = ()
    best_confidence: float | None = None


@dataclass(frozen=True)
class ResolutionResult:
    input_string: str
    entity: EntityRecord | None
    layer: Literal["deterministic", "gemini_residual", "manual_correction"] | None
    confidence: float | None
    matched_field: str | None
    audit_event: AuditEvent | None = None
    unresolved: UnresolvedMention | None = None

    @property
    def entity_id(self) -> str | None:
        return self.entity.id if self.entity else None


class GeminiMergeProposal(BaseModel):
    """Strict JSON schema for Gemini residual merge proposals."""

    model_config = ConfigDict(extra="forbid")

    input_string: str = Field(min_length=1)
    candidate_entity_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=500)

    @field_validator("input_string", "candidate_entity_id")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must be non-empty")
        return stripped


@dataclass(frozen=True)
class _IndexHit:
    entity_id: str
    matched_field: str


@dataclass
class Resolver:
    entities: Sequence[EntityRecord]
    corrections: dict[str, str] = field(default_factory=dict)
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        self._by_id = {entity.id: entity for entity in self.entities}
        self._identifier_index: dict[str, _IndexHit] = {}
        self._name_index: dict[str, list[_IndexHit]] = defaultdict(list)
        for entity in self.entities:
            self._add_identifier(entity.cik, entity.id, "cik")
            self._add_identifier(entity.ticker, entity.id, "ticker")
            self._add_identifier(entity.lei, entity.id, "lei")
            for series_id in entity.fred_series_ids:
                self._add_identifier(series_id, entity.id, "fred_series_id")
            name_values = [(entity.canonical_name, "canonical_name")]
            name_values.extend((alias, "alias") for alias in entity.aliases)
            for value, field_name in name_values:
                normalized = normalize_name(value)
                if normalized:
                    self._name_index[normalized].append(_IndexHit(entity.id, field_name))

    def _add_identifier(self, value: str | None, entity_id: str, field_name: str) -> None:
        normalized = normalize_identifier(value)
        if normalized:
            self._identifier_index[normalized] = _IndexHit(entity_id, field_name)

    @classmethod
    def from_universe_file(
        cls,
        universe_path: Path,
        *,
        corrections_path: Path | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> Resolver:
        return cls(load_universe(universe_path), load_corrections(corrections_path), clock)

    def resolve(self, input_string: str) -> ResolutionResult:
        query = input_string.strip()
        if not query:
            unresolved = UnresolvedMention(input_string=input_string, reason="no_match")
            return ResolutionResult(input_string, None, None, None, None, unresolved=unresolved)

        correction_id = self.corrections.get(query) or self.corrections.get(normalize_name(query))
        if correction_id:
            entity = self._by_id.get(correction_id)
            if entity is not None:
                return self._resolved(query, entity, "manual_correction", 1.0, "correction")

        identifier_hit = self._identifier_index.get(normalize_identifier(query))
        if identifier_hit is not None:
            entity = self._by_id[identifier_hit.entity_id]
            return self._resolved(query, entity, "deterministic", 1.0, identifier_hit.matched_field)

        name_hits = self._dedupe_hits(self._name_index.get(normalize_name(query), ()))
        if len(name_hits) == 1:
            hit = name_hits[0]
            entity = self._by_id[hit.entity_id]
            return self._resolved(query, entity, "deterministic", 1.0, hit.matched_field)
        if len(name_hits) > 1:
            candidates = tuple(hit.entity_id for hit in name_hits)
            unresolved = UnresolvedMention(
                input_string=query,
                reason="ambiguous_deterministic_match",
                candidates=candidates,
            )
            return ResolutionResult(query, None, None, None, None, unresolved=unresolved)

        unresolved = UnresolvedMention(input_string=query, reason="no_match")
        return ResolutionResult(query, None, None, None, None, unresolved=unresolved)

    def resolve_many(
        self,
        input_strings: Iterable[str],
        *,
        proposals: Iterable[GeminiMergeProposal] = (),
    ) -> tuple[list[ResolutionResult], list[AuditEvent], list[UnresolvedMention]]:
        deterministic_results = [self.resolve(item) for item in input_strings]
        proposal_by_input = self._best_proposals(proposals)
        results: list[ResolutionResult] = []
        audits: list[AuditEvent] = []
        unresolved: list[UnresolvedMention] = []

        for result in deterministic_results:
            if result.audit_event is not None:
                results.append(result)
                audits.append(result.audit_event)
                continue
            if result.unresolved is not None and result.unresolved.reason != "no_match":
                results.append(result)
                unresolved.append(result.unresolved)
                continue

            proposal = proposal_by_input.get(result.input_string)
            if proposal is None:
                results.append(result)
                if result.unresolved is not None:
                    unresolved.append(result.unresolved)
                continue

            residual_result = self._resolve_residual(result, proposal)
            results.append(residual_result)
            if residual_result.audit_event is not None:
                audits.append(residual_result.audit_event)
            if residual_result.unresolved is not None:
                unresolved.append(residual_result.unresolved)

        return results, audits, unresolved

    def _resolve_residual(
        self,
        deterministic_result: ResolutionResult,
        proposal: GeminiMergeProposal,
    ) -> ResolutionResult:
        if deterministic_result.entity is not None:
            unresolved = UnresolvedMention(
                input_string=proposal.input_string,
                reason="proposal_for_already_resolved",
                candidates=(proposal.candidate_entity_id,),
                best_confidence=proposal.confidence,
            )
            return ResolutionResult(
                proposal.input_string, None, None, None, None, unresolved=unresolved
            )
        entity = self._by_id.get(proposal.candidate_entity_id)
        if entity is None:
            unresolved = UnresolvedMention(
                input_string=proposal.input_string,
                reason="proposal_unknown_entity",
                candidates=(proposal.candidate_entity_id,),
                best_confidence=proposal.confidence,
            )
            return ResolutionResult(
                proposal.input_string, None, None, None, None, unresolved=unresolved
            )
        if proposal.confidence < ENTITY_RESOLUTION_CONFIDENCE_THRESHOLD:
            unresolved = UnresolvedMention(
                input_string=proposal.input_string,
                reason="proposal_below_threshold",
                candidates=(proposal.candidate_entity_id,),
                best_confidence=proposal.confidence,
            )
            return ResolutionResult(
                proposal.input_string, None, None, None, None, unresolved=unresolved
            )
        return self._resolved(
            proposal.input_string,
            entity,
            "gemini_residual",
            proposal.confidence,
            "gemini_candidate",
            proposal.rationale,
        )

    def _resolved(
        self,
        input_string: str,
        entity: EntityRecord,
        layer: Literal["deterministic", "gemini_residual", "manual_correction"],
        confidence: float,
        matched_field: str,
        rationale: str = "",
    ) -> ResolutionResult:
        audit = AuditEvent(
            input_string=input_string,
            matched_entity_id=entity.id,
            layer=layer,
            confidence=confidence,
            timestamp=self.clock().isoformat(),
            matched_field=matched_field,
            rationale=rationale,
        )
        return ResolutionResult(input_string, entity, layer, confidence, matched_field, audit)

    @staticmethod
    def _dedupe_hits(hits: Iterable[_IndexHit]) -> list[_IndexHit]:
        by_entity: dict[str, _IndexHit] = {}
        field_rank = {"canonical_name": 0, "alias": 1}
        for hit in hits:
            current = by_entity.get(hit.entity_id)
            current_rank = field_rank.get(current.matched_field, 99) if current else 99
            hit_rank = field_rank.get(hit.matched_field, 99)
            if current is None or hit_rank < current_rank:
                by_entity[hit.entity_id] = hit
        return list(by_entity.values())

    @staticmethod
    def _best_proposals(
        proposals: Iterable[GeminiMergeProposal],
    ) -> dict[str, GeminiMergeProposal]:
        best: dict[str, GeminiMergeProposal] = {}
        for proposal in proposals:
            current = best.get(proposal.input_string)
            if current is None or proposal.confidence > current.confidence:
                best[proposal.input_string] = proposal
        return best


def load_universe(path: Path) -> tuple[EntityRecord, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(EntityRecord.from_mapping(item) for item in payload["entities"])


def load_corrections(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    corrections: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        input_string = str(row["input_string"]).strip()
        entity_id = str(row["entity_id"]).strip()
        corrections[input_string] = entity_id
        corrections[normalize_name(input_string)] = entity_id
    return corrections


def append_jsonl(path: Path, rows: Iterable[object]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            if hasattr(row, "model_dump"):
                payload = row.model_dump()
            elif hasattr(row, "__dataclass_fields__"):
                payload = asdict(row)
            else:
                payload = row
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            count += 1
    return count

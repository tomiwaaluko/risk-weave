"""Assemble a provenanced graph from already-extracted snapshot rows (RIS-28).

This module is the **live** path that connects RIS-10 extraction rows, RIS-11
entity resolution, and RIS-9 ``DER-*`` weight derivations into the Graft 2
assembly write gate (`RW-ALG-032`).

Invariants enforced here:

* Gemini is **not** called. Weights come only from registered deterministic
  derivation methods (`RW-AI-010`, `RW-ALG-001`).
* Every edge weight is a :class:`~riskweave.derivations.WeightRecord` bound to
  validated provenance — incomplete evidence cannot become an edge
  (`RW-ALG-032`).
* ``disclosed_magnitude`` strings are converted by
  :func:`~riskweave.derivations.parse_disclosed_magnitude`, never by a model
  (`RW-ALG-002`).

Callers supply already-persisted extraction rows (or synthetic test fixtures).
DB I/O and Neo4j seeding live outside this module so unit tests stay offline.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from riskweave.derivations import (
    DerivationError,
    MagnitudeParseError,
    Provenance,
    ProvenanceError,
    WeightRecord,
    der_commodity_cost_share,
    der_concentration_disclosed,
    der_concentration_segment_share,
    der_credit_portfolio_share,
    der_duration,
    der_geo_revenue_share,
    parse_disclosed_magnitude,
)
from riskweave.derivations.methods import der_beta, der_commodity_factor_beta
from riskweave.entity_resolution import Resolver
from riskweave.entity_resolution.resolver import EntityRecord

from .assembly import (
    AssembledGraph,
    GraphAssemblyError,
    ProposedEdge,
    UniverseEntity,
    assemble,
    load_universe,
)

# Relationship types Gemini may emit → registered DER-* method (spec §12.1).
_RELATIONSHIP_METHOD: Mapping[str, str] = {
    "supplier": "DER-CONCENTRATION",
    "customer": "DER-CONCENTRATION",
    "sector_exposure": "DER-CONCENTRATION",
    "concentration": "DER-CONCENTRATION",
    "ownership_exposure": "DER-CONCENTRATION",
    "creditor": "DER-CREDIT",
    "lending": "DER-CREDIT",
    "loan_exposure": "DER-CREDIT",
    "commodity_dependency": "DER-COMMODITY",
    "geographic_exposure": "DER-GEO",
    "interest_rate_sensitivity": "DER-DURATION",
    "duration": "DER-DURATION",
    "equity_market_sensitivity": "DER-BETA",
    "market_beta": "DER-BETA",
}

GRAPH_VERSION_DEFAULT = "1.0.0"
DEFAULT_UNIVERSE_PATH = Path(__file__).resolve().parents[3] / "data" / "universe" / "entities.json"


class LiveAssemblyError(GraphAssemblyError):
    """Raised when live assembly cannot produce a graph from the given inputs."""


@dataclass(frozen=True)
class ExtractedRelationshipInput:
    """One already-persisted relationship extraction row (no Gemini call)."""

    source_entity: str
    target_entity: str
    relationship_type: str
    direction: Literal["positive", "negative"]
    disclosed_magnitude: str | None
    source_passage: str
    source_document_id: str
    char_start: int
    char_end: int
    extraction_confidence: float
    filing_date: date
    data_timestamp: datetime


@dataclass(frozen=True)
class NumericDerivationInputs:
    """Optional pre-fetched numeric inputs for methods beyond disclosed share.

    Keys are opaque edge keys (``source_id|target_id|relationship_type``) or
    entity ids, depending on the method. Callers that already joined XBRL /
    return series supply these; tests inject synthetic numbers. Gemini never
    populates this structure.
    """

    # Edge key → (numerator, denominator) for share-style XBRL fallbacks.
    segment_shares: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    geography_shares: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    commodity_cost_shares: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    credit_shares: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    # Entity / edge key → bond terms for DER-DURATION.
    duration_terms: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    # Entity / edge key → (asset_returns, market_or_commodity_returns).
    beta_series: Mapping[str, tuple[Sequence[float], Sequence[float]]] = field(default_factory=dict)
    commodity_beta_series: Mapping[str, tuple[Sequence[float], Sequence[float]]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "segment_shares", dict(self.segment_shares))
        object.__setattr__(self, "geography_shares", dict(self.geography_shares))
        object.__setattr__(self, "commodity_cost_shares", dict(self.commodity_cost_shares))
        object.__setattr__(self, "credit_shares", dict(self.credit_shares))
        object.__setattr__(
            self,
            "duration_terms",
            {k: dict(v) for k, v in dict(self.duration_terms).items()},
        )
        object.__setattr__(self, "beta_series", dict(self.beta_series))
        object.__setattr__(self, "commodity_beta_series", dict(self.commodity_beta_series))


@dataclass(frozen=True)
class LiveAssemblyReport:
    """Counters for operator / test inspection (not used as weights)."""

    relationships_seen: int
    edges_built: int
    skipped_unresolved: int
    skipped_no_weight: int
    skipped_unknown_type: int
    method_counts: Mapping[str, int]


def method_for_relationship(relationship_type: str) -> str | None:
    """Return the registered DER-* id for a relationship type, or None."""
    return _RELATIONSHIP_METHOD.get(relationship_type.strip().lower())


def edge_input_key(source_id: str, target_id: str, relationship_type: str) -> str:
    return f"{source_id}|{target_id}|{relationship_type}"


def _entity_record_to_universe(entity: EntityRecord, packs: tuple[str, ...]) -> UniverseEntity:
    return UniverseEntity(
        entity_id=entity.id,
        canonical_name=entity.canonical_name,
        entity_type=entity.entity_type,
        packs=packs,
    )


def _packs_by_id(universe_path: Path) -> dict[str, tuple[str, ...]]:
    """Load pack membership from the curated universe (Resolver omits packs)."""
    entities = load_universe(str(universe_path))
    return {e.entity_id: e.packs for e in entities}


def derive_weight_for_relationship(
    *,
    relationship_type: str,
    disclosed_magnitude: str | None,
    provenance: Provenance,
    source_id: str,
    target_id: str,
    numeric: NumericDerivationInputs | None = None,
) -> WeightRecord | None:
    """Derive a WeightRecord via a registered DER-* method, or return None.

    Never invents a number. Returns None when neither a parseable disclosed
    magnitude nor matching numeric inputs are available.
    """
    method_id = method_for_relationship(relationship_type)
    if method_id is None:
        return None

    numeric = numeric or NumericDerivationInputs()
    key = edge_input_key(source_id, target_id, relationship_type)

    try:
        if method_id == "DER-CONCENTRATION":
            return _derive_concentration(disclosed_magnitude, provenance, key, numeric)
        if method_id == "DER-CREDIT":
            return _derive_credit(disclosed_magnitude, provenance, key, numeric)
        if method_id == "DER-GEO":
            return _derive_geo(disclosed_magnitude, provenance, key, numeric)
        if method_id == "DER-COMMODITY":
            return _derive_commodity(disclosed_magnitude, provenance, key, numeric)
        if method_id == "DER-DURATION":
            return _derive_duration(provenance, key, source_id, numeric)
        if method_id == "DER-BETA":
            return _derive_beta(provenance, key, source_id, numeric)
    except (DerivationError, MagnitudeParseError, ProvenanceError):
        return None
    return None


def _parse_share(disclosed_magnitude: str | None) -> float | None:
    if disclosed_magnitude is None or not disclosed_magnitude.strip():
        return None
    return parse_disclosed_magnitude(disclosed_magnitude).value


def _derive_concentration(
    disclosed_magnitude: str | None,
    provenance: Provenance,
    key: str,
    numeric: NumericDerivationInputs,
) -> WeightRecord | None:
    share = _parse_share(disclosed_magnitude)
    if share is not None:
        return der_concentration_disclosed(share, provenance)
    pair = numeric.segment_shares.get(key)
    if pair is not None:
        return der_concentration_segment_share(pair[0], pair[1], provenance)
    return None


def _derive_credit(
    disclosed_magnitude: str | None,
    provenance: Provenance,
    key: str,
    numeric: NumericDerivationInputs,
) -> WeightRecord | None:
    share = _parse_share(disclosed_magnitude)
    if share is not None:
        # Disclosed portfolio share is already a fraction; express as share/1.0
        # so the registered DER-CREDIT callable stamps method_id + inputs.
        return der_credit_portfolio_share(share, 1.0, provenance)
    pair = numeric.credit_shares.get(key)
    if pair is not None:
        return der_credit_portfolio_share(pair[0], pair[1], provenance)
    return None


def _derive_geo(
    disclosed_magnitude: str | None,
    provenance: Provenance,
    key: str,
    numeric: NumericDerivationInputs,
) -> WeightRecord | None:
    share = _parse_share(disclosed_magnitude)
    if share is not None:
        return der_geo_revenue_share(share, 1.0, provenance)
    pair = numeric.geography_shares.get(key)
    if pair is not None:
        return der_geo_revenue_share(pair[0], pair[1], provenance)
    return None


def _derive_commodity(
    disclosed_magnitude: str | None,
    provenance: Provenance,
    key: str,
    numeric: NumericDerivationInputs,
) -> WeightRecord | None:
    share = _parse_share(disclosed_magnitude)
    if share is not None:
        return der_commodity_cost_share(share, 1.0, provenance)
    pair = numeric.commodity_cost_shares.get(key)
    if pair is not None:
        return der_commodity_cost_share(pair[0], pair[1], provenance)
    series = numeric.commodity_beta_series.get(key)
    if series is not None:
        return der_commodity_factor_beta(series[0], series[1], provenance)
    return None


def _derive_duration(
    provenance: Provenance,
    key: str,
    source_id: str,
    numeric: NumericDerivationInputs,
) -> WeightRecord | None:
    terms = numeric.duration_terms.get(key) or numeric.duration_terms.get(source_id)
    if terms is None:
        return None
    return der_duration(terms, provenance)


def _derive_beta(
    provenance: Provenance,
    key: str,
    source_id: str,
    numeric: NumericDerivationInputs,
) -> WeightRecord | None:
    series = numeric.beta_series.get(key) or numeric.beta_series.get(source_id)
    if series is None:
        return None
    return der_beta(series[0], series[1], provenance)


def assemble_live_graph(
    *,
    snapshot_id: str,
    relationships: Sequence[ExtractedRelationshipInput],
    resolver: Resolver,
    universe_path: Path | str = DEFAULT_UNIVERSE_PATH,
    graph_version: str = GRAPH_VERSION_DEFAULT,
    numeric: NumericDerivationInputs | None = None,
    require_edges: bool = True,
) -> tuple[AssembledGraph, LiveAssemblyReport]:
    """Resolve, derive, and assemble a graph from extracted relationships.

    Raises :class:`LiveAssemblyError` when there are no extraction rows, or
    when ``require_edges`` is true and no provenanced edges can be built.
    Does **not** fall back to the committed fixture — callers choose that.
    """
    if not relationships:
        raise LiveAssemblyError(
            f"no extracted relationships for snapshot {snapshot_id!r}; "
            "run Gemini extraction first, or seed with source=fixture"
        )

    universe_path = Path(universe_path)
    packs_by_id = _packs_by_id(universe_path)

    mentions: list[str] = []
    for rel in relationships:
        mentions.append(rel.source_entity)
        mentions.append(rel.target_entity)
    results, _audits, _unresolved = resolver.resolve_many(mentions)
    resolved_by_mention: dict[str, EntityRecord] = {}
    for result in results:
        if result.entity is not None:
            resolved_by_mention[result.input_string] = result.entity

    edges: list[ProposedEdge] = []
    entities_by_id: dict[str, UniverseEntity] = {}
    skipped_unresolved = 0
    skipped_no_weight = 0
    skipped_unknown_type = 0
    method_counts: dict[str, int] = {}

    for rel in relationships:
        if method_for_relationship(rel.relationship_type) is None:
            skipped_unknown_type += 1
            continue
        source = resolved_by_mention.get(rel.source_entity.strip())
        target = resolved_by_mention.get(rel.target_entity.strip())
        if source is None or target is None:
            skipped_unresolved += 1
            continue
        if source.id == target.id:
            skipped_no_weight += 1
            continue

        try:
            provenance = Provenance(
                source_document_id=rel.source_document_id,
                filing_date=rel.filing_date,
                source_passage=rel.source_passage,
                char_start=rel.char_start,
                char_end=rel.char_end,
                data_timestamp=rel.data_timestamp,
                extraction_confidence=rel.extraction_confidence,
            )
        except ProvenanceError as exc:
            # Incomplete provenance cannot become an edge (RW-ALG-032).
            raise LiveAssemblyError(
                f"extracted relationship missing valid provenance: {exc}"
            ) from exc

        record = derive_weight_for_relationship(
            relationship_type=rel.relationship_type,
            disclosed_magnitude=rel.disclosed_magnitude,
            provenance=provenance,
            source_id=source.id,
            target_id=target.id,
            numeric=numeric,
        )
        if record is None:
            skipped_no_weight += 1
            continue

        edge = ProposedEdge(
            source_id=source.id,
            target_id=target.id,
            relationship_type=rel.relationship_type.strip().lower(),
            direction=rel.direction,
            record=record,
        )
        edges.append(edge)
        method_counts[record.method_id] = method_counts.get(record.method_id, 0) + 1
        for entity in (source, target):
            if entity.id not in entities_by_id:
                packs = packs_by_id.get(entity.id, ("cre",))
                entities_by_id[entity.id] = _entity_record_to_universe(entity, packs)

    report = LiveAssemblyReport(
        relationships_seen=len(relationships),
        edges_built=len(edges),
        skipped_unresolved=skipped_unresolved,
        skipped_no_weight=skipped_no_weight,
        skipped_unknown_type=skipped_unknown_type,
        method_counts=method_counts,
    )

    if require_edges and not edges:
        raise LiveAssemblyError(
            f"live assembly for snapshot {snapshot_id!r} produced no edges "
            f"(seen={report.relationships_seen}, unresolved={report.skipped_unresolved}, "
            f"no_weight={report.skipped_no_weight}, unknown_type={report.skipped_unknown_type}); "
            "refusing to substitute the fixture"
        )

    graph = assemble(snapshot_id, graph_version, entities_by_id.values(), edges)
    return graph, report


def assemble_live_graph_from_rows(
    *,
    snapshot_id: str,
    relationships: Iterable[ExtractedRelationshipInput],
    universe_path: Path | str = DEFAULT_UNIVERSE_PATH,
    corrections_path: Path | None = None,
    graph_version: str = GRAPH_VERSION_DEFAULT,
    numeric: NumericDerivationInputs | None = None,
) -> tuple[AssembledGraph, LiveAssemblyReport]:
    """Convenience wrapper that builds a :class:`Resolver` from the universe file."""
    resolver = Resolver.from_universe_file(
        Path(universe_path),
        corrections_path=corrections_path,
    )
    return assemble_live_graph(
        snapshot_id=snapshot_id,
        relationships=tuple(relationships),
        resolver=resolver,
        universe_path=universe_path,
        graph_version=graph_version,
        numeric=numeric,
    )

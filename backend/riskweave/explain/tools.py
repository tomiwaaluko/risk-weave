"""The closed §13.2 deterministic tool registry Gemini may call (RIS-19).

`RW-AI-002`/`RW-SEC-002` are MUST-level: Gemini orchestrates the backend only
through function calling against **this fixed registry** — the ten tools of spec
§13.2 — and nothing else. Arbitrary tool or code execution is prohibited. This
module is where that closure is enforced *server-side*, independently of
whatever the model asks for:

* :class:`ClosedToolRegistry` exposes exactly the §13.2 tool names. An
  :meth:`~ClosedToolRegistry.invoke` for any other name raises
  :class:`UnknownToolError` — the refusal is not advisory prompt text, it is a
  hard rejection in code.
* Every call's arguments are validated against the tool's closed JSON schema
  (:class:`ToolSpec`) before the handler runs; an unexpected or missing argument
  raises :class:`ToolArgumentError`.
* Handlers are **deterministic** and read only *approved run state* bundled in a
  :class:`RunToolContext` — the propagation result, the graph snapshot, pre-baked
  provenance, and the shipped Graft 1/3 breach-distance and duration functions.
  They never call a model and never invent a number.

Crucially, only *computed* outputs enter a :class:`ToolResult`'s ``numbers`` set
(the numbers the Q&A answer is later allowed to state). A magnitude or id the
model passes as a tool **argument** is never laundered into that set — otherwise
the model could smuggle a fabricated figure past the numeric-containment guard
(`RW-AI-011`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from riskweave.breach.distance import BreachDistance, CovenantThreshold, breach_distance
from riskweave.derivations.duration import modified_duration
from riskweave.derivations.provenance import Provenance
from riskweave.propagation import PropagationResult
from riskweave.propagation.graph import GraphSnapshot

from .generation import EdgeEvidence


class ToolError(ValueError):
    """Base class for a rejected or unsatisfiable tool call."""


class UnknownToolError(ToolError):
    """Raised when a requested tool is not in the closed §13.2 registry."""


class ToolArgumentError(ToolError):
    """Raised when a call's arguments violate the tool's closed schema."""


# Minimal JSON-schema type name -> accepted Python types. ``bool`` is excluded
# from every numeric slot explicitly in :meth:`ToolSpec.validate`.
_JSON_TYPES: Mapping[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "object": (dict,),
}


# --------------------------------------------------------------------------- #
# Results                                                                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ToolResult:
    """The deterministic outcome of one tool call.

    ``payload`` is the JSON-serializable body fed back to Gemini. ``numbers`` are
    the *computed* figures this result contributes to the answer's allowed-number
    payload (never argument values). ``citations`` are provenance records the
    answer may then cite; each carries a stable ``citation_id``.
    """

    payload: dict[str, object]
    numbers: tuple[float, ...] = ()
    citations: tuple[EdgeEvidence, ...] = ()


# --------------------------------------------------------------------------- #
# Tool specifications (names + closed argument schemas)                        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ToolSpec:
    """One §13.2 tool: its name, description, and closed argument schema.

    ``properties`` maps each accepted argument to a minimal JSON-schema type
    (``string`` | ``number`` | ``integer`` | ``object``). ``required`` lists the
    arguments that must be present. Validation is deliberately strict and closed:
    an argument not in ``properties`` is rejected rather than ignored.
    """

    name: str
    description: str
    properties: Mapping[str, str]
    required: tuple[str, ...]

    def declaration(self) -> dict[str, object]:
        """Gemini ``functionDeclarations`` entry for this tool."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    arg: {"type": json_type} for arg, json_type in self.properties.items()
                },
                "required": list(self.required),
            },
        }

    def validate(self, args: object) -> dict[str, object]:
        """Return validated args, or raise :class:`ToolArgumentError`.

        Enforces: args is an object, no unexpected keys (closed schema), all
        required keys present, and each present value matches its declared type.
        """
        if not isinstance(args, dict):
            raise ToolArgumentError(f"{self.name}: arguments must be an object")
        for key in args:
            if key not in self.properties:
                raise ToolArgumentError(f"{self.name}: unexpected argument {key!r}")
        for key in self.required:
            if key not in args:
                raise ToolArgumentError(f"{self.name}: missing required argument {key!r}")
        for key, value in args.items():
            expected = self.properties[key]
            allowed = _JSON_TYPES.get(expected, ())
            # bool is an int in Python; never accept it for a number/integer slot.
            if isinstance(value, bool) or not isinstance(value, allowed):
                raise ToolArgumentError(f"{self.name}: argument {key!r} must be of type {expected}")
        return dict(args)


# The ten tools of spec §13.2 — this tuple *is* the closed registry surface.
_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "resolve_entity",
        "Resolve a natural-language entity name to its canonical graph node id.",
        {"name": "string"},
        ("name",),
    ),
    ToolSpec(
        "get_company_exposures",
        "List a node's outgoing weighted, provenanced exposure edges.",
        {"entity_id": "string"},
        ("entity_id",),
    ),
    ToolSpec(
        "run_scenario",
        "Return the top ranked impacts of the current bound scenario run.",
        {"scenario_params": "object"},
        (),
    ),
    ToolSpec(
        "propagate_shock",
        "Return the bound run's contributions attributable to one shock factor.",
        {"factor_id": "string", "magnitude": "number"},
        ("factor_id",),
    ),
    ToolSpec(
        "get_propagation_paths",
        "Return the decomposed transmission paths reaching an entity in the run.",
        {"entity_id": "string", "scenario_id": "string"},
        ("entity_id",),
    ),
    ToolSpec(
        "calculate_breach_distance",
        "Compute covenant breach distance for an entity under the bound run (Graft 1).",
        {"entity_id": "string", "scenario_id": "string"},
        ("entity_id",),
    ),
    ToolSpec(
        "calculate_duration",
        "Compute modified duration for a debt security (Graft 3).",
        {"security_id": "string"},
        ("security_id",),
    ),
    ToolSpec(
        "get_ratio",
        "Return a pre-derived financial ratio for an entity with its provenance.",
        {"entity_id": "string", "ratio_name": "string"},
        ("entity_id", "ratio_name"),
    ),
    ToolSpec(
        "retrieve_filing_passage",
        "Retrieve an exact quoted filing passage by provenance id.",
        {"provenance_id": "string"},
        ("provenance_id",),
    ),
    ToolSpec(
        "retrieve_fred_series",
        "Retrieve a FRED economic time series by id.",
        {"series_id": "string", "range": "string"},
        ("series_id",),
    ),
)

TOOL_NAMES: frozenset[str] = frozenset(spec.name for spec in _SPECS)


# --------------------------------------------------------------------------- #
# Run-scoped context the handlers read (approved run state only)               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SecurityTerms:
    """Bond terms for a duration calculation (Graft 3 inputs)."""

    coupon_rate: float
    yield_rate: float
    years_to_maturity: float
    payments_per_year: int = 2


@dataclass(frozen=True)
class RunToolContext:
    """Everything the §13.2 handlers are allowed to read for one run.

    Only ``scenario_id``, ``result``, ``snapshot``, ``provenance_by_edge`` and
    the display-name maps are required; the graft/reference data
    (``covenant_thresholds``, ``securities``, ``ratios``, ``fred_series``) is
    optional and, when absent, the corresponding tool returns a structured
    "no data on file" result so the answer withholds rather than improvises.
    """

    scenario_id: str
    result: PropagationResult
    snapshot: GraphSnapshot
    provenance_by_edge: Mapping[str, EdgeEvidence]
    node_names: Mapping[str, str]
    node_types: Mapping[str, str]
    covenant_thresholds: Mapping[str, tuple[CovenantThreshold, float]] = field(default_factory=dict)
    securities: Mapping[str, SecurityTerms] = field(default_factory=dict)
    ratios: Mapping[tuple[str, str], tuple[float, str]] = field(default_factory=dict)
    fred_series: Mapping[str, tuple[tuple[str, float], ...]] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Registry                                                                     #
# --------------------------------------------------------------------------- #
Handler = Callable[[dict[str, object]], ToolResult]


class ClosedToolRegistry:
    """The closed set of tools plus their bound, deterministic handlers.

    Constructed via :func:`build_registry`. :meth:`invoke` is the single entry
    point: it rejects any name outside §13.2 and any schema-invalid arguments
    *before* dispatching — the server, not the prompt, is the boundary.
    """

    def __init__(self, handlers: Mapping[str, Handler]) -> None:
        self._specs = {spec.name: spec for spec in _SPECS}
        missing = set(self._specs) - set(handlers)
        if missing:
            raise ValueError(f"registry missing handlers for: {sorted(missing)}")
        self._handlers = dict(handlers)

    @property
    def tool_names(self) -> frozenset[str]:
        return TOOL_NAMES

    def declarations(self) -> list[dict[str, object]]:
        """Gemini ``functionDeclarations`` for every tool, in §13.2 order."""
        return [spec.declaration() for spec in _SPECS]

    def invoke(self, name: str, args: object) -> ToolResult:
        """Validate and run one tool call; raise on unknown tool / bad args."""
        spec = self._specs.get(name)
        if spec is None:
            raise UnknownToolError(f"tool {name!r} is not in the closed §13.2 registry; refused")
        validated = spec.validate(args)
        return self._handlers[name](validated)


def build_registry(context: RunToolContext) -> ClosedToolRegistry:
    """Bind the ten §13.2 handlers to one run's approved state."""
    return ClosedToolRegistry(
        {
            "resolve_entity": lambda a: _resolve_entity(context, a),
            "get_company_exposures": lambda a: _get_company_exposures(context, a),
            "run_scenario": lambda a: _run_scenario(context, a),
            "propagate_shock": lambda a: _propagate_shock(context, a),
            "get_propagation_paths": lambda a: _get_propagation_paths(context, a),
            "calculate_breach_distance": lambda a: _calculate_breach_distance(context, a),
            "calculate_duration": lambda a: _calculate_duration(context, a),
            "get_ratio": lambda a: _get_ratio(context, a),
            "retrieve_filing_passage": lambda a: _retrieve_filing_passage(context, a),
            "retrieve_fred_series": lambda a: _retrieve_fred_series(context, a),
        }
    )


# --------------------------------------------------------------------------- #
# Handlers                                                                     #
# --------------------------------------------------------------------------- #
_MISSING_CITATION_ID = "cit-tool"


def _citation_for(context: RunToolContext, edge_id: str) -> EdgeEvidence | None:
    """The provenance record for an edge, tagged with a stable citation id."""
    base = context.provenance_by_edge.get(edge_id)
    if base is None:
        return None
    citation_id = f"cit-{edge_id}"
    return EdgeEvidence(
        citation_id=citation_id,
        edge_id=base.edge_id,
        source_name=context.node_names.get(base.edge_id, base.source_name),
        target_name=base.target_name,
        relationship_type=base.relationship_type,
        method_id=base.method_id,
        source_document_id=base.source_document_id,
        source_passage=base.source_passage,
        char_start=base.char_start,
        char_end=base.char_end,
        filing_date=base.filing_date,
        data_timestamp=base.data_timestamp,
        extraction_confidence=base.extraction_confidence,
    )


def _resolve_entity(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    query = str(args["name"]).strip().lower()
    for node in context.snapshot.nodes:
        name = context.node_names.get(node.node_id, node.name)
        if name.lower() == query or query in name.lower() or node.node_id.lower() == query:
            return ToolResult(
                payload={
                    "node_id": node.node_id,
                    "name": name,
                    "node_type": context.node_types.get(node.node_id, node.node_type),
                }
            )
    return ToolResult(payload={"node_id": None, "name": None, "resolved": False})


def _get_company_exposures(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    entity_id = str(args["entity_id"])
    if not context.snapshot.has_node(entity_id):
        return ToolResult(payload={"entity_id": entity_id, "resolved": False, "outgoing_edges": []})
    numbers: list[float] = []
    citations: list[EdgeEvidence] = []
    edges: list[dict[str, object]] = []
    for edge in context.snapshot.outgoing(entity_id):
        numbers.append(edge.weight)
        citation = _citation_for(context, edge.edge_id)
        cit_id = citation.citation_id if citation else None
        if citation is not None:
            citations.append(citation)
        edges.append(
            {
                "edge_id": edge.edge_id,
                "target_id": edge.target_id,
                "target_name": context.node_names.get(edge.target_id, edge.target_id),
                "weight": edge.weight,
                "method_id": edge.method_id,
                "citation_id": cit_id,
            }
        )
    return ToolResult(
        payload={"entity_id": entity_id, "outgoing_edges": edges},
        numbers=tuple(numbers),
        citations=tuple(citations),
    )


def _ranked_impacts(
    context: RunToolContext, limit: int = 5
) -> tuple[list[dict[str, object]], list[float]]:
    numbers: list[float] = [
        context.result.damping,
        context.result.floor,
        float(context.result.max_hops),
    ]
    rows: list[dict[str, object]] = []
    for impact in context.result.ranked_entities()[:limit]:
        numbers.extend((impact.risk_score, impact.raw_impact))
        rows.append(
            {
                "node_id": impact.node_id,
                "name": context.node_names.get(impact.node_id, impact.node_id),
                "risk_score": impact.risk_score,
                "raw_impact": impact.raw_impact,
            }
        )
    return rows, numbers


def _run_scenario(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    rows, numbers = _ranked_impacts(context)
    return ToolResult(
        payload={
            "scenario_id": context.scenario_id,
            "damping": context.result.damping,
            "floor": context.result.floor,
            "max_hops": context.result.max_hops,
            "top_impacts": rows,
            "note": "Run is bound to its committed factors and magnitudes (run-scoped Q&A).",
        },
        numbers=tuple(numbers),
    )


def _propagate_shock(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    factor_id = str(args["factor_id"])
    numbers: list[float] = []
    citations: list[EdgeEvidence] = []
    rows: list[dict[str, object]] = []
    for impact in context.result.impacts.values():
        for contribution in impact.contributions:
            if contribution.factor_id != factor_id:
                continue
            numbers.append(contribution.contribution)
            numbers.append(float(contribution.hop_count))
            for edge in contribution.edges:
                numbers.append(edge.weight)
                citation = _citation_for(context, edge.edge_id)
                if citation is not None:
                    citations.append(citation)
            rows.append(
                {
                    "node_id": impact.node_id,
                    "name": context.node_names.get(impact.node_id, impact.node_id),
                    "hop_count": contribution.hop_count,
                    "contribution": contribution.contribution,
                }
            )
    return ToolResult(
        payload={
            "factor_id": factor_id,
            "contributions": rows,
            "note": "Magnitudes are bound to the committed run; the argument does not recompute.",
        },
        numbers=tuple(numbers),
        citations=tuple(citations),
    )


def _get_propagation_paths(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    entity_id = str(args["entity_id"])
    impact = context.result.impacts.get(entity_id)
    if impact is None:
        return ToolResult(payload={"entity_id": entity_id, "impacted": False, "paths": []})
    numbers: list[float] = [impact.risk_score, impact.raw_impact]
    citations: list[EdgeEvidence] = []
    paths: list[dict[str, object]] = []
    for contribution in impact.contributions:
        numbers.append(contribution.contribution)
        numbers.append(float(contribution.hop_count))
        edge_cits: list[str] = []
        for edge in contribution.edges:
            numbers.append(edge.weight)
            citation = _citation_for(context, edge.edge_id)
            if citation is not None:
                citations.append(citation)
                edge_cits.append(citation.citation_id)
        paths.append(
            {
                "factor_id": contribution.factor_id,
                "hop_count": contribution.hop_count,
                "contribution": contribution.contribution,
                "edge_ids": [e.edge_id for e in contribution.edges],
                "method_ids": [e.method_id for e in contribution.edges],
                "citation_ids": edge_cits,
            }
        )
    return ToolResult(
        payload={"entity_id": entity_id, "risk_score": impact.risk_score, "paths": paths},
        numbers=tuple(numbers),
        citations=tuple(citations),
    )


def _provenance_citation(entity_id: str, provenance: Provenance) -> EdgeEvidence:
    """Wrap a raw :class:`Provenance` as a citable evidence record."""
    return EdgeEvidence(
        citation_id=f"cit-cov-{entity_id}",
        edge_id=f"covenant:{entity_id}",
        source_name=entity_id,
        target_name=entity_id,
        relationship_type="covenant_threshold",
        method_id="DER-CREDIT",
        source_document_id=provenance.source_document_id,
        source_passage=provenance.source_passage,
        char_start=provenance.char_start,
        char_end=provenance.char_end,
        filing_date=provenance.filing_date.isoformat(),
        data_timestamp=provenance.data_timestamp.isoformat(),
        extraction_confidence=provenance.extraction_confidence,
    )


def _calculate_breach_distance(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    entity_id = str(args["entity_id"])
    entry = context.covenant_thresholds.get(entity_id)
    if entry is None:
        return ToolResult(
            payload={
                "entity_id": entity_id,
                "available": False,
                "note": "No covenant threshold on file for this entity.",
            }
        )
    threshold, current_ratio = entry
    impact = context.result.impacts.get(entity_id)
    node_impact = impact.raw_impact if impact is not None else 0.0
    distance: BreachDistance = breach_distance(threshold, current_ratio, node_impact)
    citation = _provenance_citation(entity_id, threshold.provenance)
    return ToolResult(
        payload={
            "entity_id": entity_id,
            "available": True,
            "kind": distance.kind.value,
            "current_value": distance.current_value,
            "threshold_value": distance.threshold_value,
            "projected_value": distance.projected_value,
            "headroom": distance.headroom,
            "tier": distance.tier.value,
            "breached": distance.breached,
            "citation_id": citation.citation_id,
        },
        numbers=(
            distance.current_value,
            distance.threshold_value,
            distance.projected_value,
            distance.headroom,
        ),
        citations=(citation,),
    )


def _calculate_duration(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    security_id = str(args["security_id"])
    terms = context.securities.get(security_id)
    if terms is None:
        return ToolResult(
            payload={
                "security_id": security_id,
                "available": False,
                "note": "No bond terms on file for this security.",
            }
        )
    duration = modified_duration(
        terms.coupon_rate,
        terms.yield_rate,
        terms.years_to_maturity,
        terms.payments_per_year,
    )
    return ToolResult(
        payload={
            "security_id": security_id,
            "available": True,
            "modified_duration": duration,
        },
        numbers=(duration,),
    )


def _get_ratio(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    entity_id = str(args["entity_id"])
    ratio_name = str(args["ratio_name"])
    entry = context.ratios.get((entity_id, ratio_name))
    if entry is None:
        return ToolResult(
            payload={
                "entity_id": entity_id,
                "ratio_name": ratio_name,
                "available": False,
                "note": "No pre-derived ratio on file.",
            }
        )
    value, provenance_ref = entry
    return ToolResult(
        payload={
            "entity_id": entity_id,
            "ratio_name": ratio_name,
            "available": True,
            "value": value,
            "provenance_ref": provenance_ref,
        },
        numbers=(value,),
    )


def _retrieve_filing_passage(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    provenance_id = str(args["provenance_id"])
    for edge_id, evidence in context.provenance_by_edge.items():
        if provenance_id in (evidence.source_document_id, edge_id, evidence.edge_id):
            citation = _citation_for(context, evidence.edge_id) or evidence
            return ToolResult(
                payload={
                    "provenance_id": provenance_id,
                    "source_document_id": evidence.source_document_id,
                    "passage": evidence.source_passage,
                    "char_start": evidence.char_start,
                    "char_end": evidence.char_end,
                    "citation_id": citation.citation_id,
                },
                numbers=(float(evidence.char_start), float(evidence.char_end)),
                citations=(citation,),
            )
    return ToolResult(payload={"provenance_id": provenance_id, "found": False})


def _retrieve_fred_series(context: RunToolContext, args: dict[str, object]) -> ToolResult:
    series_id = str(args["series_id"])
    values = context.fred_series.get(series_id)
    if not values:
        return ToolResult(payload={"series_id": series_id, "available": False, "values": []})
    numbers = tuple(v for _, v in values)
    return ToolResult(
        payload={
            "series_id": series_id,
            "available": True,
            "values": [{"date": d, "value": v} for d, v in values],
        },
        numbers=numbers,
    )

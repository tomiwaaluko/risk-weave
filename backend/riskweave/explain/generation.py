"""Evidence-bound explanation generation via Gemini (RIS-19, `RW-AI-011`).

Gemini writes the prose; deterministic code owns every number. After a scenario
runs, this module turns the computation payload for one impacted node into a
short natural-language explanation through a **real Gemini call**, then gates the
generated text with the already-merged numeric-containment guard
(:func:`riskweave.explain.guard_explanation`). The flow is:

1. Build a :class:`NodeExplanationContext` containing *only* computation output
   (risk score, raw impact, per-path contributions, hop counts, engine
   constants) plus pre-baked provenance passages tagged with citation ids. Raw
   filings and any chat history are never in the prompt (`RW-SEC-002`).
2. Ask Gemini for strict JSON ``{"explanation": ..., "citations": [...]}``.
3. Guard the prose: every numeric token must exist in the payload
   (`RW-AI-011`), and every cited id must resolve to a provenance record.
4. On failure, regenerate **once** with a corrective note; if it still fails,
   return the labeled structured-numbers fallback and never the offending prose.

The module is transport-agnostic: it depends only on the ``create_interaction``
shape shared with :class:`riskweave_api.extraction.gemini.GeminiTransport`, so
unit tests inject a fake and the live path passes the real REST transport.

Explanations come in the three audience variants the spec requires (`RW-FR-022`,
:class:`Audience`); the voice differs but the numeric-containment guard is
identical across all three. The second half of the RIS-19 AI surface —
run-scoped Q&A via Gemini tool orchestration against the closed §13.2 registry —
lives in :mod:`riskweave.explain.qa` and :mod:`riskweave.explain.tools`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from riskweave.propagation import PropagationResult

from .guard import ExplanationPayload, guard_explanation
from .payload import payload_for_node

# Pro tier is the spec default for explanation generation (`RW-AI-003`); the
# caller may override, but this is the sensible default the endpoint uses.
DEFAULT_EXPLANATION_MODEL = "gemini-3.1-pro-preview"
EXPLANATION_PROMPT_VERSION = "node-explanation-v1"

# How many top-ranked contributing paths (and their evidence) to surface. The
# demo explanation is short; the tail paths are visible in the evidence panel.
DEFAULT_TOP_PATHS = 4

# Citation markers look like ``[cit-1]``. They are stripped before the numeric
# guard runs so a marker's own digits never count as an unsupported number.
_CITATION_MARKER_RE = re.compile(r"\[(cit-[A-Za-z0-9_-]+)\]")


class Audience(StrEnum):
    """The three explanation audiences the spec requires (`RW-FR-022`).

    Only the framing/voice line of the prompt varies by audience; the numeric
    payload, the evidence, and the numeric-containment guard (`RW-AI-011`) are
    identical across all three — a student explanation is held to the same
    "only payload numbers" invariant as an analyst one.
    """

    ANALYST = "analyst"
    STUDENT = "student"
    RETAIL = "retail"


# Audience-specific voice guidance. These change tone and framing only; they
# never relax the HARD RULES or introduce numbers.
_AUDIENCE_VOICE: dict[Audience, str] = {
    Audience.ANALYST: (
        "for a financial analyst. Be precise and terse; use the sector/credit "
        "transmission vocabulary an analyst expects."
    ),
    Audience.STUDENT: (
        "for a finance student learning how contagion propagates. Briefly name the "
        "mechanism (e.g. sector concentration, credit exposure) in plain terms so "
        "the 'why' is instructive, without adding any figure that is not listed."
    ),
    Audience.RETAIL: (
        "for a non-expert retail reader. Use plain, jargon-free language and explain "
        "what the transmission means in everyday terms. Do not give advice."
    ),
}


class ExplanationTransport(Protocol):
    """The single Gemini call shape this module needs (see ``GeminiTransport``)."""

    def create_interaction(self, **kwargs: object) -> dict[str, object]:
        """Return at least ``{"output_text": <str>}`` for the given prompt."""


# --------------------------------------------------------------------------- #
# Evidence + context (the only things the prompt is built from)                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EdgeEvidence:
    """One provenance record, tagged with the citation id Gemini may reference.

    Carries the pre-baked Graft 2 fields (`RW-ALG-032`) for one contributing
    edge so a cited claim resolves to an exact filing passage. Dates are ISO
    strings so the record serializes verbatim to the API response.
    """

    citation_id: str
    edge_id: str
    source_name: str
    target_name: str
    relationship_type: str
    method_id: str
    source_document_id: str
    source_passage: str
    char_start: int
    char_end: int
    filing_date: str
    data_timestamp: str
    extraction_confidence: float


@dataclass(frozen=True)
class PathSummary:
    """A ranked contributing path as presented to Gemini (numbers only)."""

    factor_id: str
    hop_count: int
    contribution: float
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class NodeExplanationContext:
    """The closed computation + provenance bundle a node explanation is built from.

    Everything Gemini is allowed to see lives here: computed figures and
    citation-tagged provenance passages, nothing else.
    """

    node_id: str
    node_name: str
    node_type: str
    risk_score: float
    raw_impact: float
    path_count: int
    damping: float
    floor: float
    max_hops: int
    paths: tuple[PathSummary, ...]
    evidence: tuple[EdgeEvidence, ...]

    def evidence_by_id(self) -> dict[str, EdgeEvidence]:
        return {e.citation_id: e for e in self.evidence}


@dataclass(frozen=True)
class StructuredNumber:
    """One labeled figure for the guard-failure fallback (verified, never prose)."""

    label: str
    value: float
    citation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedExplanation:
    """Outcome of one explanation request.

    On success ``prose`` is the guarded text and ``citations`` are the evidence
    records it references. On guard failure after the single retry,
    ``used_fallback`` is True, ``prose`` is ``None``, and ``structured_numbers``
    carries the labeled verified figures shown instead — the offending prose is
    never returned (`RW-AI-011`).
    """

    node_id: str
    prose: str | None
    citations: tuple[EdgeEvidence, ...]
    structured_numbers: tuple[StructuredNumber, ...]
    used_fallback: bool
    attempts: int
    guard_violations: tuple[str, ...]
    model: str
    audience: Audience = Audience.ANALYST
    input_token_count: int | None = None
    output_token_count: int | None = None


# --------------------------------------------------------------------------- #
# Building the context + guard payload from a propagation result               #
# --------------------------------------------------------------------------- #
def build_node_context(
    result: PropagationResult,
    node_id: str,
    *,
    node_name: str,
    node_type: str,
    provenance_by_edge: dict[str, EdgeEvidence],
    node_names: dict[str, str] | None = None,
    top_paths: int = DEFAULT_TOP_PATHS,
) -> tuple[NodeExplanationContext, ExplanationPayload]:
    """Assemble the presented context and the matching guard payload.

    ``provenance_by_edge`` maps an ``edge_id`` to its (un-tagged) evidence; this
    function assigns stable ``cit-N`` ids in path-rank order. The returned
    payload is :func:`payload_for_node` augmented with the exact integers the
    context presents (path count), so a legitimately cited figure is never
    rejected and nothing outside the computation slips through.
    """
    impact = result.impacts[node_id]
    ranked = impact.contributions[: max(0, top_paths)]

    names = node_names or {}
    evidence: list[EdgeEvidence] = []
    edge_to_citation: dict[str, str] = {}
    path_summaries: list[PathSummary] = []

    for contribution in ranked:
        cit_ids: list[str] = []
        for edge in contribution.edges:
            if edge.edge_id not in edge_to_citation:
                base = provenance_by_edge.get(edge.edge_id)
                if base is None:
                    continue  # No pre-baked provenance for this edge; skip citing it.
                citation_id = f"cit-{len(evidence) + 1}"
                edge_to_citation[edge.edge_id] = citation_id
                evidence.append(
                    EdgeEvidence(
                        citation_id=citation_id,
                        edge_id=edge.edge_id,
                        source_name=names.get(edge.source_id, edge.source_id),
                        target_name=names.get(edge.target_id, edge.target_id),
                        relationship_type=base.relationship_type,
                        method_id=edge.method_id,
                        source_document_id=base.source_document_id,
                        source_passage=base.source_passage,
                        char_start=base.char_start,
                        char_end=base.char_end,
                        filing_date=base.filing_date,
                        data_timestamp=base.data_timestamp,
                        extraction_confidence=base.extraction_confidence,
                    )
                )
            cit_ids.append(edge_to_citation[edge.edge_id])
        path_summaries.append(
            PathSummary(
                factor_id=contribution.factor_id,
                hop_count=contribution.hop_count,
                contribution=contribution.contribution,
                citation_ids=tuple(dict.fromkeys(cit_ids)),
            )
        )

    context = NodeExplanationContext(
        node_id=node_id,
        node_name=node_name,
        node_type=node_type,
        risk_score=impact.risk_score,
        raw_impact=impact.raw_impact,
        path_count=len(impact.contributions),
        damping=result.damping,
        floor=result.floor,
        max_hops=result.max_hops,
        paths=tuple(path_summaries),
        evidence=tuple(evidence),
    )

    base_payload = payload_for_node(result, node_id)
    # The context also presents these integers verbatim; add them so a truthful
    # explanation citing them is not flagged.
    augmented = ExplanationPayload(
        numbers=(*base_payload.numbers, float(len(impact.contributions)), float(len(ranked)))
    )
    return context, augmented


# --------------------------------------------------------------------------- #
# Generation + guarding                                                        #
# --------------------------------------------------------------------------- #
def generate_node_explanation(
    context: NodeExplanationContext,
    payload: ExplanationPayload,
    transport: ExplanationTransport,
    *,
    audience: Audience = Audience.ANALYST,
    model: str = DEFAULT_EXPLANATION_MODEL,
    max_attempts: int = 2,
) -> GeneratedExplanation:
    """Generate, guard, retry once, then fall back to verified structured numbers.

    ``max_attempts`` is the initial call plus retries (2 → one regeneration, the
    RIS-19 policy). Every attempt is guarded for numeric containment
    (`RW-AI-011`) and citation resolvability; the first passing attempt wins.
    ``audience`` selects the voice variant (`RW-FR-022`); it changes only the
    prompt's framing line, never the guard.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")

    known_citations = context.evidence_by_id()
    last_violations: tuple[str, ...] = ()
    correction: str | None = None
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None

    for attempt in range(1, max_attempts + 1):
        prompt = _build_prompt(context, correction, audience)
        response = transport.create_interaction(
            model=model,
            input=prompt,
            temperature=0,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": _RESPONSE_SCHEMA,
            },
        )
        input_tokens_total, output_tokens_total = _accumulate_usage(
            response, input_tokens_total, output_tokens_total
        )
        text, cited_ids, parse_error = _parse_response(str(response.get("output_text", "")))
        if parse_error is not None:
            last_violations = (parse_error,)
            correction = (
                f"Your previous reply was not valid JSON ({parse_error}). Return strict JSON."
            )
            continue

        violations = _validate(text, cited_ids, payload, known_citations)
        if not violations:
            resolved = _resolve_citations(text, cited_ids, known_citations)
            return GeneratedExplanation(
                node_id=context.node_id,
                prose=text,
                citations=resolved,
                structured_numbers=_structured_numbers(context),
                used_fallback=False,
                attempts=attempt,
                guard_violations=(),
                model=model,
                audience=audience,
                input_token_count=input_tokens_total,
                output_token_count=output_tokens_total,
            )
        last_violations = violations
        correction = (
            "Your previous explanation used numbers or citations that are not permitted: "
            f"{', '.join(violations)}. Use ONLY the figures listed under FIGURES, and cite "
            "ONLY the listed citation ids. Do not introduce any other number."
        )

    # Exhausted retries: never surface the offending prose (`RW-AI-011`).
    return GeneratedExplanation(
        node_id=context.node_id,
        prose=None,
        citations=context.evidence,
        structured_numbers=_structured_numbers(context),
        used_fallback=True,
        attempts=max_attempts,
        guard_violations=last_violations,
        model=model,
        audience=audience,
        input_token_count=input_tokens_total,
        output_token_count=output_tokens_total,
    )


def _accumulate_usage(
    response: dict[str, object], input_total: int | None, output_total: int | None
) -> tuple[int | None, int | None]:
    """Sum token usage across retries — every attempt is a real billed call (RIS-34)."""
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return input_total, output_total
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    new_input = input_total if input_tokens is None else int(input_tokens) + (input_total or 0)
    new_output = output_total if output_tokens is None else int(output_tokens) + (output_total or 0)
    return new_input, new_output


_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "explanation": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["explanation", "citations"],
    "additionalProperties": False,
}


def strip_citation_markers(text: str) -> str:
    """Remove ``[cit-N]`` markers so their digits are not mistaken for figures."""
    return _CITATION_MARKER_RE.sub("", text)


def citation_markers_in(text: str) -> tuple[str, ...]:
    """Every citation id referenced inline in ``text`` (marker form)."""
    return tuple(m.group(1) for m in _CITATION_MARKER_RE.finditer(text))


def _validate(
    text: str,
    cited_ids: tuple[str, ...],
    payload: ExplanationPayload,
    known_citations: dict[str, EdgeEvidence],
) -> tuple[str, ...]:
    """Return every reason the explanation is unacceptable (empty tuple = ok)."""
    violations: list[str] = []
    guard = guard_explanation(strip_citation_markers(text), payload)
    violations.extend(guard.unsupported)
    # Both the declared citations array and any inline markers must resolve.
    for cid in {*cited_ids, *citation_markers_in(text)}:
        if cid not in known_citations:
            violations.append(cid)
    return tuple(dict.fromkeys(violations))


def _resolve_citations(
    text: str,
    cited_ids: tuple[str, ...],
    known_citations: dict[str, EdgeEvidence],
) -> tuple[EdgeEvidence, ...]:
    """The evidence records the explanation actually references, in first-seen order."""
    ordered: list[EdgeEvidence] = []
    seen: set[str] = set()
    for cid in (*citation_markers_in(text), *cited_ids):
        record = known_citations.get(cid)
        if record is not None and cid not in seen:
            seen.add(cid)
            ordered.append(record)
    return tuple(ordered)


def _parse_response(output_text: str) -> tuple[str, tuple[str, ...], str | None]:
    """Parse the strict-JSON reply into (explanation, citations, error)."""
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as exc:
        return "", (), str(exc)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("explanation"), str):
        return "", (), "response missing a string 'explanation' field"
    raw_citations = parsed.get("citations", [])
    citations = tuple(str(c) for c in raw_citations) if isinstance(raw_citations, list) else ()
    return parsed["explanation"], citations, None


def _structured_numbers(context: NodeExplanationContext) -> tuple[StructuredNumber, ...]:
    """Labeled verified figures — the fallback shown when prose fails the guard."""
    numbers: list[StructuredNumber] = [
        StructuredNumber("Risk score", round(context.risk_score, 1)),
        StructuredNumber("Raw impact", round(context.raw_impact, 4)),
        StructuredNumber("Contributing paths", float(context.path_count)),
    ]
    for index, path in enumerate(context.paths, start=1):
        numbers.append(
            StructuredNumber(
                label=f"Path {index} contribution ({path.hop_count} hop"
                f"{'s' if path.hop_count != 1 else ''})",
                value=round(path.contribution, 4),
                citation_ids=path.citation_ids,
            )
        )
    return tuple(numbers)


# --------------------------------------------------------------------------- #
# Prompt construction                                                          #
# --------------------------------------------------------------------------- #
def _build_prompt(
    context: NodeExplanationContext,
    correction: str | None,
    audience: Audience = Audience.ANALYST,
) -> str:
    figures = _figures_block(context)
    evidence = _evidence_block(context)
    correction_block = f"\nCORRECTION:\n{correction}\n" if correction else ""
    voice = _AUDIENCE_VOICE[audience]
    return (
        "You are RiskWeave's explanation writer. Write a short, plain explanation "
        "(2-4 sentences) of why the entity below carries the computed scenario risk, "
        f"{voice}\n\n"
        "HARD RULES:\n"
        "- Use ONLY numbers that appear verbatim under FIGURES. Never invent, estimate, "
        "combine, or round-derive any other number. This is a strict requirement.\n"
        "- Support each material claim with a citation id in square brackets, e.g. [cit-1], "
        "drawn ONLY from the ids under EVIDENCE.\n"
        "- Do not give price predictions or buy/sell/hold advice. Describe transmission only.\n"
        '- Return STRICT JSON: {"explanation": string, "citations": [string, ...]} where '
        "citations lists every id you referenced.\n\n"
        f"ENTITY: {context.node_name} (type: {context.node_type})\n\n"
        f"FIGURES:\n{figures}\n\n"
        f"EVIDENCE:\n{evidence}\n"
        f"{correction_block}"
    )


def _fmt(value: float, places: int) -> str:
    return f"{value:.{places}f}"


def _figures_block(context: NodeExplanationContext) -> str:
    lines = [
        f"- risk_score: {_fmt(context.risk_score, 1)} (0-100 display score, not a probability)",
        f"- raw_impact: {_fmt(context.raw_impact, 4)}",
        f"- contributing_paths: {context.path_count}",
        f"- damping_per_hop: {_fmt(context.damping, 2)}",
        f"- max_hops: {context.max_hops}",
    ]
    for index, path in enumerate(context.paths, start=1):
        cits = " ".join(f"[{c}]" for c in path.citation_ids)
        lines.append(
            f"- path_{index}: contribution {_fmt(path.contribution, 4)} over "
            f"{path.hop_count} hop(s) from factor {path.factor_id} {cits}".rstrip()
        )
    return "\n".join(lines)


def _evidence_block(context: NodeExplanationContext) -> str:
    if not context.evidence:
        return "(no citable evidence for this node)"
    lines = []
    for evidence in context.evidence:
        lines.append(
            f"- {evidence.citation_id}: {evidence.source_name} -> {evidence.target_name} "
            f"({evidence.relationship_type}, method {evidence.method_id}); "
            f'"{evidence.source_passage}" '
            f"[{evidence.source_document_id} filed {evidence.filing_date}]"
        )
    return "\n".join(lines)

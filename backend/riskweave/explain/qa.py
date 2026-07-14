"""Run-scoped Q&A via Gemini function calling (RIS-19, journey §8.3).

This is the second half of the RIS-19 AI surface: the user asks a free-text
question *about a completed run*, and Gemini answers **only** by orchestrating
the closed §13.2 tool registry (:mod:`riskweave.explain.tools`) — never from
memory, never with an invented number.

The control loop here is the trust boundary. Each model turn is either a tool
call or a final answer:

* a tool call is validated and executed by :class:`ClosedToolRegistry`; an
  unknown tool or a schema-invalid argument is refused *server-side* and the
  refusal is fed back so the model must recover (`RW-AI-002`, `RW-SEC-002`);
* every executed call — and every refusal — is recorded in a per-session
  :class:`ToolCallAudit` log (tool name, arguments, result hash, timestamp): the
  concrete answer to "what if it hallucinates";
* the final answer is held to the **same** numeric-containment + citation guard
  as explanations (`RW-AI-011`, `RW-FR-024`): every numeric token must exist in
  the accumulated approved payload (run state + the results of the tools this
  session actually called), and every citation must resolve to a real provenance
  record. If it cannot pass after one correction, the answer is **withheld** —
  the offending prose is never surfaced.

Only *computed* tool outputs enter the allowed-number payload; a figure the
model passes as a tool argument is never trusted (see :mod:`.tools`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from .generation import (
    DEFAULT_EXPLANATION_MODEL,
    Audience,
    EdgeEvidence,
    _resolve_citations,
    _validate,
)
from .guard import ExplanationPayload
from .tools import ClosedToolRegistry, ToolArgumentError, UnknownToolError

QA_PROMPT_VERSION = "run-scoped-qa-v1"

# Bounds on one session: how many tool calls before we give up, and how many
# times a guard-failing final answer may be corrected before it is withheld.
DEFAULT_MAX_TOOL_CALLS = 8
DEFAULT_MAX_ANSWER_RETRIES = 1


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------- #
# Transport                                                                    #
# --------------------------------------------------------------------------- #
class QaToolTransport(Protocol):
    """One function-calling turn against Gemini.

    Given the running ``messages`` (abstract turns, see :func:`_render_messages`)
    and the tool ``declarations``, return a normalized dict that is **either**
    ``{"function_call": {"name": str, "args": dict}}`` or ``{"output_text": str}``
    (a final answer as strict JSON ``{"answer": str, "citations": [str, ...]}``).
    """

    def create_tool_interaction(self, **kwargs: object) -> dict[str, object]: ...


# --------------------------------------------------------------------------- #
# Audit log                                                                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ToolCallAudit:
    """One entry in the per-session tool-call audit log.

    ``status`` is ``"ok"`` for an executed call, or ``"unknown_tool"`` /
    ``"invalid_args"`` for a refused one. ``result_hash`` is a stable sha256 over
    the JSON result (or the refusal message) — enough to prove after the fact
    exactly what deterministic data the answer was built from.
    """

    tool_name: str
    args: dict[str, object]
    result_hash: str
    status: str
    timestamp: str


def _hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


# --------------------------------------------------------------------------- #
# Answer                                                                       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class QaAnswer:
    """The outcome of one run-scoped Q&A session.

    On success ``answer`` is the guarded prose and ``withheld`` is False. When no
    grounded answer could be produced, ``withheld`` is True, ``answer`` is None,
    and ``reason`` / ``guard_violations`` explain why — the unsupported prose is
    never returned (`RW-FR-024`).
    """

    session_id: str
    question: str
    audience: Audience
    answer: str | None
    withheld: bool
    reason: str | None
    citations: tuple[EdgeEvidence, ...]
    audit: tuple[ToolCallAudit, ...]
    tool_call_count: int
    answer_attempts: int
    guard_violations: tuple[str, ...]
    model: str


# --------------------------------------------------------------------------- #
# Message assembly (abstract turns the transport renders)                      #
# --------------------------------------------------------------------------- #
def _system_preamble() -> str:
    return (
        "You are RiskWeave's run-scoped analyst assistant. Answer the user's question "
        "ONLY using the provided tools, which read the approved results of one completed "
        "scenario run. HARD RULES:\n"
        "- Never state a number that a tool did not return. If you need a figure, call the "
        "tool that computes it first.\n"
        "- Support every material claim with a citation id in square brackets, e.g. [cit-1], "
        "taken only from tool results.\n"
        "- If the tools cannot support an answer, explicitly say you cannot answer from the "
        "available run data. Do not guess, estimate, or use outside knowledge.\n"
        "- No price predictions and no buy/sell/hold advice.\n"
        'When you are ready to answer, reply with STRICT JSON: {"answer": string, '
        '"citations": [string, ...]}.'
    )


def _render_messages(
    question: str,
    turns: list[dict[str, object]],
) -> list[dict[str, object]]:
    """The full abstract conversation: preamble + question, then every turn."""
    head: list[dict[str, object]] = [
        {"kind": "user_text", "text": _system_preamble()},
        {"kind": "user_text", "text": f"QUESTION: {question}"},
    ]
    return head + turns


# --------------------------------------------------------------------------- #
# Answer parsing                                                               #
# --------------------------------------------------------------------------- #
def _parse_answer(output_text: str) -> tuple[str, tuple[str, ...], str | None]:
    """Parse a strict-JSON final answer into (answer, citations, error)."""
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as exc:
        return "", (), str(exc)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
        return "", (), "response missing a string 'answer' field"
    raw = parsed.get("citations", [])
    citations = tuple(str(c) for c in raw) if isinstance(raw, list) else ()
    return parsed["answer"], citations, None


# --------------------------------------------------------------------------- #
# The session loop                                                             #
# --------------------------------------------------------------------------- #
def answer_question(
    question: str,
    registry: ClosedToolRegistry,
    transport: QaToolTransport,
    *,
    session_id: str,
    base_payload: ExplanationPayload,
    known_citations: dict[str, EdgeEvidence] | None = None,
    audience: Audience = Audience.ANALYST,
    model: str = DEFAULT_EXPLANATION_MODEL,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    max_answer_retries: int = DEFAULT_MAX_ANSWER_RETRIES,
    clock: Callable[[], str] = _utc_now_iso,
) -> QaAnswer:
    """Run one run-scoped Q&A session and return a guarded answer or a withholding.

    The loop alternates model turns: a tool call is validated + executed (or
    refused) by ``registry`` and logged; a final answer is guarded for numeric
    containment and citation resolvability against the *accumulated* payload
    (``base_payload`` plus every executed tool's computed numbers). The first
    answer that passes wins; otherwise it is corrected once, then withheld.
    """
    allowed_numbers: list[float] = list(base_payload.numbers)
    citations: dict[str, EdgeEvidence] = dict(known_citations or {})
    audit: list[ToolCallAudit] = []
    turns: list[dict[str, object]] = []
    tool_calls = 0
    answer_attempts = 0

    # Generous absolute bound so a pathological model can't loop forever.
    max_steps = max_tool_calls + max_answer_retries + 2
    for _ in range(max_steps):
        response = transport.create_tool_interaction(
            model=model,
            messages=_render_messages(question, turns),
            tools=registry.declarations(),
            temperature=0,
        )

        function_call = response.get("function_call")
        if isinstance(function_call, dict):
            if tool_calls >= max_tool_calls:
                break
            tool_calls += 1
            name = str(function_call.get("name", ""))
            raw_args = function_call.get("args")
            args = raw_args if isinstance(raw_args, dict) else {}
            turns.append({"kind": "model_call", "name": name, "args": args})
            try:
                result = registry.invoke(name, args)
            except UnknownToolError as exc:
                audit.append(
                    ToolCallAudit(name, dict(args), _hash_json(str(exc)), "unknown_tool", clock())
                )
                turns.append(
                    {
                        "kind": "tool_error",
                        "name": name,
                        "error": "Tool is not in the closed registry and was refused.",
                    }
                )
                continue
            except ToolArgumentError as exc:
                audit.append(
                    ToolCallAudit(name, dict(args), _hash_json(str(exc)), "invalid_args", clock())
                )
                turns.append({"kind": "tool_error", "name": name, "error": str(exc)})
                continue

            allowed_numbers.extend(result.numbers)
            for citation in result.citations:
                citations[citation.citation_id] = citation
            audit.append(ToolCallAudit(name, dict(args), _hash_json(result.payload), "ok", clock()))
            turns.append({"kind": "tool_result", "name": name, "response": result.payload})
            continue

        # A final answer.
        answer_attempts += 1
        text, cited_ids, parse_error = _parse_answer(str(response.get("output_text", "")))
        if parse_error is not None:
            if answer_attempts <= max_answer_retries:
                turns.append(
                    {
                        "kind": "user_text",
                        "text": (
                            f"Your reply was not valid JSON ({parse_error}). Return strict JSON."
                        ),
                    }
                )
                continue
            return _withhold(
                session_id,
                question,
                audience,
                citations,
                audit,
                tool_calls,
                answer_attempts,
                (parse_error,),
                model,
                reason="final answer was not valid JSON",
            )

        payload = ExplanationPayload(numbers=tuple(allowed_numbers))
        violations = _validate(text, cited_ids, payload, citations)
        if not violations:
            resolved = _resolve_citations(text, cited_ids, citations)
            return QaAnswer(
                session_id=session_id,
                question=question,
                audience=audience,
                answer=text,
                withheld=False,
                reason=None,
                citations=resolved,
                audit=tuple(audit),
                tool_call_count=tool_calls,
                answer_attempts=answer_attempts,
                guard_violations=(),
                model=model,
            )

        if answer_attempts <= max_answer_retries:
            turns.append(
                {
                    "kind": "user_text",
                    "text": (
                        "Your answer used numbers or citations that are not supported by tool "
                        f"results: {', '.join(violations)}. Either call the tool that produces "
                        "them, or explicitly state you cannot answer from the available run data."
                    ),
                }
            )
            continue

        return _withhold(
            session_id,
            question,
            audience,
            citations,
            audit,
            tool_calls,
            answer_attempts,
            violations,
            model,
            reason="answer failed the numeric-containment/citation guard",
        )

    # Tool-call budget exhausted without a grounded answer.
    return _withhold(
        session_id,
        question,
        audience,
        citations,
        audit,
        tool_calls,
        answer_attempts,
        (),
        model,
        reason="tool-call budget exhausted without a grounded answer",
    )


def _withhold(
    session_id: str,
    question: str,
    audience: Audience,
    citations: dict[str, EdgeEvidence],
    audit: list[ToolCallAudit],
    tool_calls: int,
    answer_attempts: int,
    violations: tuple[str, ...],
    model: str,
    *,
    reason: str,
) -> QaAnswer:
    return QaAnswer(
        session_id=session_id,
        question=question,
        audience=audience,
        answer=None,
        withheld=True,
        reason=reason,
        citations=(),
        audit=tuple(audit),
        tool_call_count=tool_calls,
        answer_attempts=answer_attempts,
        guard_violations=violations,
        model=model,
    )

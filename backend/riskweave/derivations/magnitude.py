"""Deterministic parser for ``disclosed_magnitude`` strings (spec `RW-ALG-002`).

Gemini captures a verbatim magnitude phrase into a string; this parser — never
the model — validates it and converts it to a number. It **rejects** anything it
cannot parse unambiguously rather than guessing (`RW-PRIN-008`), because a wrong
number that looks confident is the project's defining failure mode.

Examples
--------
>>> parse_disclosed_magnitude("approximately 28% of operating expenses").value
0.28
>>> parse_disclosed_magnitude("between 25% and 30% of revenue").is_range
True
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class MagnitudeParseError(ValueError):
    """Raised when a disclosed-magnitude string cannot be parsed unambiguously."""


# Qualifier phrases we recognise. Each maps a matched phrase to a stable flag.
_APPROX_WORDS = (
    "approximately",
    "approximate",
    "approx.",
    "approx",
    "about",
    "around",
    "roughly",
    "nearly",
    "~",
)
_LOWER_BOUND_WORDS = (
    "at least",
    "no less than",
    "more than",
    "greater than",
    "in excess of",
    "over",
)
_UPPER_BOUND_WORDS = ("at most", "no more than", "less than", "up to", "under")

# A percentage token, optionally trailed by a footnote marker like "(1)", "[2]",
# a superscript digit, or an asterisk/dagger. The footnote is captured and
# discarded — it is not part of the number.
_PCT = r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)"
_FOOTNOTE = r"(?:\s*(?:\(\d{1,3}\)|\[\d{1,3}\]|[¹²³⁰-⁹]+|[*†‡]))?"

_RANGE_RE = re.compile(
    rf"{_PCT}{_FOOTNOTE}\s*(?:-|–|—|to|and)\s*{_PCT}{_FOOTNOTE}",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(rf"{_PCT}{_FOOTNOTE}", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedMagnitude:
    """Structured result of parsing a disclosed-magnitude string.

    Attributes
    ----------
    value:
        The magnitude as a fraction in ``[0, 1]``. For a range this is the
        midpoint (and ``is_range`` is set so callers may treat it as uncertain).
    raw:
        The original input string, preserved for provenance.
    is_approximate:
        True if the disclosure hedged the figure ("approximately", "~", ...).
    is_range:
        True if the disclosure gave a range rather than a point value.
    range_low, range_high:
        The range endpoints as fractions, or ``None`` for a point value.
    bound:
        ``"lower"`` / ``"upper"`` if the disclosure gave a one-sided bound
        ("at least 20%"), else ``None``.
    qualifiers:
        The verbatim qualifier phrases detected, for audit.
    """

    value: float
    raw: str
    is_approximate: bool
    is_range: bool
    range_low: float | None
    range_high: float | None
    bound: str | None
    qualifiers: tuple[str, ...]


def _to_fraction(pct_text: str) -> float:
    pct = float(pct_text)
    if not (0.0 <= pct <= 100.0):
        raise MagnitudeParseError(
            f"percentage {pct} is outside the plausible [0, 100] range for a share"
        )
    return pct / 100.0


def parse_disclosed_magnitude(text: str) -> ParsedMagnitude:
    """Parse a disclosed-magnitude string into a fraction, or raise.

    Only percentage-of-something disclosures are accepted (the shape §12.1
    relies on). Qualitative phrases ("a significant portion"), empty strings,
    and unparseable garbage are rejected.
    """

    if not isinstance(text, str):
        raise MagnitudeParseError("disclosed_magnitude must be a string")
    raw = text
    normalized = text.strip().lower()
    if not normalized:
        raise MagnitudeParseError("disclosed_magnitude is empty")

    qualifiers: list[str] = []
    is_approximate = any(w in normalized for w in _APPROX_WORDS)
    if is_approximate:
        qualifiers.extend(w for w in _APPROX_WORDS if w in normalized)

    bound: str | None = None
    if any(w in normalized for w in _LOWER_BOUND_WORDS):
        bound = "lower"
        qualifiers.extend(w for w in _LOWER_BOUND_WORDS if w in normalized)
    elif any(w in normalized for w in _UPPER_BOUND_WORDS):
        bound = "upper"
        qualifiers.extend(w for w in _UPPER_BOUND_WORDS if w in normalized)

    # Try a range first (it is a superset match of the single pattern).
    range_match = _RANGE_RE.search(normalized)
    if range_match:
        low = _to_fraction(range_match.group(1))
        high = _to_fraction(range_match.group(2))
        if low > high:
            low, high = high, low
        return ParsedMagnitude(
            value=(low + high) / 2.0,
            raw=raw,
            is_approximate=is_approximate,
            is_range=True,
            range_low=low,
            range_high=high,
            bound=bound,
            qualifiers=tuple(dict.fromkeys(qualifiers)),
        )

    matches = _SINGLE_RE.findall(normalized)
    if not matches:
        raise MagnitudeParseError(f"no parseable percentage in disclosed_magnitude: {raw!r}")
    if len(matches) > 1:
        # Two unrelated percentages with no range connective is ambiguous —
        # refuse rather than pick one (RW-PRIN-008).
        raise MagnitudeParseError(f"ambiguous: multiple percentages without a range in {raw!r}")

    value = _to_fraction(matches[0])
    return ParsedMagnitude(
        value=value,
        raw=raw,
        is_approximate=is_approximate,
        is_range=False,
        range_low=None,
        range_high=None,
        bound=bound,
        qualifiers=tuple(dict.fromkeys(qualifiers)),
    )

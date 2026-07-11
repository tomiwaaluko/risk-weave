"""Evidence-bound explanation guard (`RW-AI-011`, `RW-FR-023`).

The hard invariant: **every numeric token in a generated explanation must exist
in the computation payload.** Gemini writes prose; this deterministic check
refuses any explanation that introduces a number the computation did not
produce. It is the post-generation gate the spec requires tests to assert.

The guard is model-free and pure. It:

1. builds an allowed-number set from a :class:`ExplanationPayload` (the only
   numbers Gemini is permitted to have seen — computation outputs + provenance
   figures), and
2. extracts every numeric token from candidate text and checks membership,
   tolerant of formatting (thousands separators, %, $, x-multiples, parenthesised
   negatives, rounding to the payload's precision).

Numbers are compared by value with a relative tolerance, because an explanation
may legitimately round ``4.812`` to ``4.8``. A token matches if it equals any
allowed number at the allowed number's display precision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# Matches integers/decimals with optional sign, $, thousands separators, %, and
# a trailing x-multiple. Years and ids are numbers too — the payload must
# include any that legitimately appear (e.g. a filing year in provenance).
_NUMBER_RE = re.compile(
    r"""
    \(?                     # optional opening paren (negative accounting style)
    -?                      # optional sign
    \$?                     # optional currency
    \d{1,3}(?:,\d{3})+      # grouped thousands
    (?:\.\d+)?              # optional fraction
    |
    \(?-?\$?\d+(?:\.\d+)?   # plain integer/decimal
    """,
    re.VERBOSE,
)


def _to_decimal(token: str) -> Decimal | None:
    """Parse a display token into a Decimal, or None if it isn't numeric."""
    cleaned = token.strip().strip(")").lstrip("(")
    negative = cleaned.startswith("(") or token.strip().startswith("(") or cleaned.startswith("-")
    cleaned = cleaned.replace(",", "").replace("$", "").replace("%", "").lstrip("-")
    cleaned = cleaned.rstrip("xX")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -value if negative else value


@dataclass(frozen=True)
class ExplanationPayload:
    """The closed set of numbers an explanation is allowed to reference.

    Populate ``numbers`` from the computation result (risk scores, path
    contributions, weights, ratios, breach values) and any provenance figures
    (filing years, disclosed magnitudes). Nothing else may appear in the text.
    """

    numbers: tuple[float, ...]
    _allowed: tuple[Decimal, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        allowed = []
        for n in self.numbers:
            if isinstance(n, bool) or not isinstance(n, int | float):
                raise TypeError("payload numbers must be real numbers")
            allowed.append(Decimal(str(n)))
        object.__setattr__(self, "_allowed", tuple(allowed))

    @classmethod
    def from_values(cls, *values: float) -> ExplanationPayload:
        return cls(numbers=tuple(values))

    def permits(self, value: Decimal, rel_tol: Decimal = Decimal("0.005")) -> bool:
        """True if ``value`` matches an allowed number at display precision.

        A candidate matches an allowed number ``a`` if, when both are rounded to
        the number of decimal places shown in the candidate, they are equal — or
        if they agree within ``rel_tol`` relative tolerance (rounding of ``a``).
        """
        for allowed in self._allowed:
            if allowed == value:
                return True
            exponent = value.as_tuple().exponent
            places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
            quant = Decimal(1).scaleb(-places)
            if allowed.quantize(quant) == value.quantize(quant):
                return True
            if allowed != 0 and abs(allowed - value) <= abs(allowed) * rel_tol:
                return True
            if allowed == 0 and abs(value) <= rel_tol:
                return True
        return False


@dataclass(frozen=True)
class GuardResult:
    """Outcome of guarding one explanation."""

    ok: bool
    unsupported: tuple[str, ...]  # numeric tokens with no payload match


def extract_numeric_tokens(text: str) -> tuple[str, ...]:
    """Every numeric token in ``text`` (as displayed, formatting preserved)."""
    return tuple(m.group(0) for m in _NUMBER_RE.finditer(text))


def guard_explanation(text: str, payload: ExplanationPayload) -> GuardResult:
    """Reject an explanation containing any number absent from ``payload``.

    Returns a :class:`GuardResult`; ``ok`` is False and ``unsupported`` lists the
    offending tokens if the text introduces an unsupported number
    (`RW-AI-011`, `RW-FR-024`).
    """
    unsupported: list[str] = []
    for token in extract_numeric_tokens(text):
        value = _to_decimal(token)
        if value is None:
            continue
        if not payload.permits(value):
            unsupported.append(token)
    return GuardResult(ok=not unsupported, unsupported=tuple(unsupported))

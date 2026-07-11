"""Adversarial tests for the disclosed-magnitude parser (RW-ALG-002, RW-PRIN-008)."""

from __future__ import annotations

import pytest

from riskweave.derivations import MagnitudeParseError, parse_disclosed_magnitude


def test_plain_percentage():
    result = parse_disclosed_magnitude("28% of operating expenses")
    assert result.value == pytest.approx(0.28)
    assert not result.is_approximate
    assert not result.is_range


def test_approximately_sets_flag():
    result = parse_disclosed_magnitude("approximately 28% of operating expenses")
    assert result.value == pytest.approx(0.28)
    assert result.is_approximate


@pytest.mark.parametrize(
    "text",
    [
        "about 15 percent",
        "roughly 15%",
        "~15%",
        "around 15%",
    ],
)
def test_approximate_synonyms(text):
    result = parse_disclosed_magnitude(text)
    assert result.value == pytest.approx(0.15)
    assert result.is_approximate


@pytest.mark.parametrize(
    "text",
    [
        "between 25% and 30% of revenue",
        "25% to 30%",
        "25%-30%",
        "25% – 30%",
    ],
)
def test_ranges_midpoint(text):
    result = parse_disclosed_magnitude(text)
    assert result.is_range
    assert result.range_low == pytest.approx(0.25)
    assert result.range_high == pytest.approx(0.30)
    assert result.value == pytest.approx(0.275)


def test_reversed_range_is_normalized():
    result = parse_disclosed_magnitude("30% to 25%")
    assert result.range_low == pytest.approx(0.25)
    assert result.range_high == pytest.approx(0.30)
    assert result.value == pytest.approx(0.275)


@pytest.mark.parametrize(
    "text,value",
    [
        ("28%(1)", 0.28),
        ("28%[2]", 0.28),
        ("28%*", 0.28),
        ("28%¹", 0.28),  # superscript footnote marker
    ],
)
def test_footnote_markers_stripped(text, value):
    result = parse_disclosed_magnitude(text)
    assert result.value == pytest.approx(value)


def test_lower_bound_flag():
    result = parse_disclosed_magnitude("at least 20% of revenue")
    assert result.value == pytest.approx(0.20)
    assert result.bound == "lower"


def test_upper_bound_flag():
    result = parse_disclosed_magnitude("up to 40% of revenue")
    assert result.value == pytest.approx(0.40)
    assert result.bound == "upper"


def test_decimal_percentage():
    result = parse_disclosed_magnitude("12.5%")
    assert result.value == pytest.approx(0.125)


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "   ",
        "a significant portion of revenue",
        "material to our results",
        "several suppliers",
        "no numbers here at all",
    ],
)
def test_rejects_qualitative_and_empty(garbage):
    with pytest.raises(MagnitudeParseError):
        parse_disclosed_magnitude(garbage)


def test_rejects_ambiguous_multiple_percentages():
    # Two unrelated percentages with no range connective — refuse, don't guess.
    with pytest.raises(MagnitudeParseError):
        parse_disclosed_magnitude("10% here and also unrelated 90% elsewhere in the filing")


def test_rejects_out_of_domain_percentage():
    with pytest.raises(MagnitudeParseError):
        parse_disclosed_magnitude("150% of operating expenses")


def test_deterministic():
    text = "approximately 28% of operating expenses"
    assert parse_disclosed_magnitude(text) == parse_disclosed_magnitude(text)

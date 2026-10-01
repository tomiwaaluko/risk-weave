from decimal import Decimal

from riskweave_api.extraction.cli import SPEND_CAP_USD, should_stop


def test_extraction_continues_at_the_eighteen_dollar_cap() -> None:
    assert should_stop(Decimal("18.00"), SPEND_CAP_USD) is False


def test_extraction_stops_when_recorded_spend_exceeds_eighteen_dollars() -> None:
    assert should_stop(Decimal("18.01"), SPEND_CAP_USD) is True

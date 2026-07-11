"""Shared fixtures for the derivation tests."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from riskweave.derivations import Provenance


@pytest.fixture
def provenance() -> Provenance:
    """A valid provenance whose offsets exactly span its passage."""
    passage = "fuel was approximately 28% of operating expenses"
    return Provenance(
        source_document_id="0000320193-24-000123",
        filing_date=date(2024, 2, 1),
        source_passage=passage,
        char_start=1000,
        char_end=1000 + len(passage),
        data_timestamp=datetime(2024, 2, 1, 0, 0, 0),
        extraction_confidence=0.95,
    )

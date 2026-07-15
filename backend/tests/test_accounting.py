from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from riskweave.accounting.pricing import PricingError, estimate_cost_usd
from riskweave_api.accounting.models import GeminiUsageRecord
from riskweave_api.accounting.service import BudgetExceededError, GeminiAccountingService
from riskweave_api.extraction.gemini import GEMINI_EXTRACTION_MODEL, GeminiExtractionClient
from riskweave_api.extraction.service import ExtractionService
from riskweave_api.ingestion.clients import FredClient, SecClient
from riskweave_api.ingestion.models import (
    Base,
    DataSnapshot,
    Document,
    DocumentChunk,
    SnapshotMember,
)
from riskweave_api.ingestion.rate_limit import RateLimiter


@contextmanager
def _session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_snapshot(session: Session) -> tuple[DataSnapshot, DocumentChunk]:
    document = Document(
        source_document_id="0000000001-24-000001",
        cik="0000000001",
        accession_number="0000000001-24-000001",
        form="10-K",
        filing_date=date(2024, 1, 1),
        source_url="https://www.sec.gov/Archives/example.htm",
        retrieved_at=datetime.now(UTC),
        content_hash="doc-hash",
        canonical_text="Acme lends to Beta through a $50 million facility.",
        provider_metadata={},
        normalization_map={"strategy": "test"},
    )
    chunk = DocumentChunk(
        ordinal=0,
        text=document.canonical_text,
        char_start=0,
        char_end=len(document.canonical_text),
        overlap_start=None,
        overlap_end=None,
        content_hash="chunk-hash",
    )
    document.chunks.append(chunk)
    snapshot = DataSnapshot(
        name="fixture", manifest_hash="snapshot-hash", frozen_at=datetime.now(UTC), manifest_json={}
    )
    session.add_all([document, snapshot])
    session.flush()
    session.add(
        SnapshotMember(
            snapshot_id=snapshot.id,
            record_type="document",
            record_id=document.accession_number,
            content_hash=document.content_hash,
        )
    )
    session.flush()
    return snapshot, chunk


def test_estimate_cost_computes_pricing_from_measured_tokens() -> None:
    cost = estimate_cost_usd("gemini-3.5-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == Decimal("0.075") + Decimal("0.30")


def test_estimate_cost_rejects_unregistered_model() -> None:
    with pytest.raises(PricingError):
        estimate_cost_usd("gemini-not-a-real-model", input_tokens=1, output_tokens=1)


def test_record_logs_a_call_and_computes_cost() -> None:
    service = GeminiAccountingService(
        soft_daily_budget_usd=Decimal("5"), hard_daily_budget_usd=Decimal("20")
    )
    with _session() as session:
        record = service.record(
            session,
            purpose="extraction",
            model="gemini-3.5-flash",
            input_tokens=1000,
            output_tokens=200,
        )
        assert record is not None
        assert record.cost_usd == estimate_cost_usd("gemini-3.5-flash", 1000, 200)
        assert session.query(GeminiUsageRecord).count() == 1


def test_record_skips_without_raising_when_tokens_are_missing() -> None:
    service = GeminiAccountingService(
        soft_daily_budget_usd=Decimal("5"), hard_daily_budget_usd=Decimal("20")
    )
    with _session() as session:
        record = service.record(
            session,
            purpose="explanation",
            model="gemini-3.1-pro-preview",
            input_tokens=None,
            output_tokens=10,
        )
        assert record is None
        assert session.query(GeminiUsageRecord).count() == 0


def test_budget_status_reports_soft_and_hard_breaches() -> None:
    service = GeminiAccountingService(
        soft_daily_budget_usd=Decimal("0.01"), hard_daily_budget_usd=Decimal("0.02")
    )
    with _session() as session:
        service.record(
            session,
            purpose="extraction",
            model="gemini-3.5-flash",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        status = service.budget_status(session)
        assert status.spent_usd == Decimal("0.075")
        assert status.soft_breached is True
        assert status.hard_breached is True


def test_check_budget_or_raise_only_gates_extraction_purpose() -> None:
    service = GeminiAccountingService(
        soft_daily_budget_usd=Decimal("0.01"), hard_daily_budget_usd=Decimal("0.02")
    )
    with _session() as session:
        service.record(
            session,
            purpose="extraction",
            model="gemini-3.5-flash",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        # Interactive purposes stay open even past the hard threshold (reliable
        # demo behavior outranks cost, spec §0.4).
        service.check_budget_or_raise(session, purpose="explanation")
        service.check_budget_or_raise(session, purpose="qa")
        with pytest.raises(BudgetExceededError):
            service.check_budget_or_raise(session, purpose="extraction")


def test_rollup_groups_by_day_purpose_and_model() -> None:
    service = GeminiAccountingService(
        soft_daily_budget_usd=Decimal("5"), hard_daily_budget_usd=Decimal("20")
    )
    today = datetime.now(UTC).date()
    with _session() as session:
        service.record(
            session,
            purpose="extraction",
            model="gemini-3.5-flash",
            input_tokens=1000,
            output_tokens=100,
        )
        service.record(
            session,
            purpose="extraction",
            model="gemini-3.5-flash",
            input_tokens=2000,
            output_tokens=200,
        )
        service.record(
            session,
            purpose="qa",
            model="gemini-3.1-pro-preview",
            input_tokens=500,
            output_tokens=50,
        )
        rows = service.rollup(session, start=today, end=today)
    by_purpose = {row.purpose: row for row in rows}
    assert by_purpose["extraction"].calls == 2
    assert by_purpose["extraction"].input_tokens == 3000
    assert by_purpose["extraction"].output_tokens == 300
    assert by_purpose["qa"].calls == 1


def test_extraction_service_refuses_further_calls_past_hard_budget() -> None:
    class _CountingTransport:
        def __init__(self) -> None:
            self.calls = 0

        def create_interaction(self, **kwargs: object) -> dict[str, object]:
            self.calls += 1
            return {
                "output_text": (
                    '{"relationships": [{"source_entity": "Acme", "target_entity": "Beta", '
                    '"relationship_type": "credit", "direction": "positive", '
                    '"disclosed_magnitude": "$50 million", "source_passage": '
                    '"Acme lends to Beta through a $50 million facility.", '
                    '"passage_location": {"source_document_id": "0000000001-24-000001", '
                    '"char_start": 0, "char_end": 51}, "extraction_confidence": 0.9}]}'
                ),
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
            }

    accounting = GeminiAccountingService(
        soft_daily_budget_usd=Decimal("0.01"), hard_daily_budget_usd=Decimal("0.02")
    )
    with _session() as session:
        snapshot, chunk = _seed_snapshot(session)
        # Pre-breach the hard budget so the very first extraction call is refused.
        accounting.record(
            session,
            purpose="extraction",
            model="gemini-3.5-flash",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        transport = _CountingTransport()
        client = GeminiExtractionClient(transport)
        service = ExtractionService(session, client=client, accounting=accounting)
        with pytest.raises(BudgetExceededError):
            service.extract_relationships_for_chunk(snapshot.id, chunk.id)
        assert transport.calls == 0


def test_extraction_service_snapshot_batch_halts_gracefully_past_hard_budget() -> None:
    class _FixedTransport:
        def create_interaction(self, **kwargs: object) -> dict[str, object]:
            return {
                "output_text": '{"relationships": []}',
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
            }

    accounting = GeminiAccountingService(
        soft_daily_budget_usd=Decimal("5"), hard_daily_budget_usd=Decimal("0.075")
    )
    with _session() as session:
        snapshot, chunk = _seed_snapshot(session)
        second_chunk = DocumentChunk(
            document_id=chunk.document_id,
            ordinal=1,
            text="No disclosed relationships here.",
            char_start=200,
            char_end=232,
            overlap_start=None,
            overlap_end=None,
            content_hash="second-chunk-hash",
        )
        session.add(second_chunk)
        session.flush()
        client = GeminiExtractionClient(_FixedTransport())
        service = ExtractionService(session, client=client, accounting=accounting)
        # Must not raise: the batch halts gracefully once the first chunk's
        # billed call reaches the hard threshold, instead of crashing the loop.
        result = service.extract_relationships_for_snapshot(snapshot.id)
        assert result.inserted == 0
        # Only the first chunk was ever billed; the second was refused before
        # any Gemini call was made.
        assert session.query(GeminiUsageRecord).count() == 1


def test_extraction_service_records_usage_after_a_successful_call() -> None:
    class _FixedTransport:
        def create_interaction(self, **kwargs: object) -> dict[str, object]:
            return {
                "output_text": '{"relationships": []}',
                "usage": {"input_tokens": 500, "output_tokens": 50},
            }

    accounting = GeminiAccountingService(
        soft_daily_budget_usd=Decimal("5"), hard_daily_budget_usd=Decimal("20")
    )
    with _session() as session:
        snapshot, chunk = _seed_snapshot(session)
        client = GeminiExtractionClient(_FixedTransport())
        service = ExtractionService(session, client=client, accounting=accounting)
        service.extract_relationships_for_chunk(snapshot.id, chunk.id)
        records = session.query(GeminiUsageRecord).all()
        assert len(records) == 1
        assert records[0].purpose == "extraction"
        assert records[0].model == GEMINI_EXTRACTION_MODEL
        assert records[0].input_tokens == 500
        assert records[0].output_tokens == 50


def test_record_best_effort_never_raises_on_a_broken_session_factory() -> None:
    service = GeminiAccountingService(
        soft_daily_budget_usd=Decimal("5"), hard_daily_budget_usd=Decimal("20")
    )

    def broken_session_factory() -> Session:
        raise RuntimeError("db unavailable")

    service.record_best_effort(
        broken_session_factory,
        purpose="explanation",
        model="gemini-3.1-pro-preview",
        input_tokens=10,
        output_tokens=5,
    )


def test_sec_client_reports_request_count_and_configured_fair_use_limit() -> None:
    calls: list[float] = []
    limiter = RateLimiter(1_000, clock=lambda: 0.0, sleep=calls.append)
    client = SecClient(
        "RiskWeave contact@example.com", limiter=limiter, fair_use_requests_per_second=10
    )
    stats_before = client.usage_stats()
    assert stats_before["request_count"] == 0
    assert stats_before["fair_use_requests_per_second"] == 10
    assert stats_before["user_agent"] == "RiskWeave contact@example.com"


def test_fred_client_reports_request_count_and_configured_rate_limit() -> None:
    client = FredClient("test-key", limiter=RateLimiter(1_000), rate_limit_requests_per_minute=120)
    stats = client.usage_stats()
    assert stats["request_count"] == 0
    assert stats["rate_limit_requests_per_minute"] == 120

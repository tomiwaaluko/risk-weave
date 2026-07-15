from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from riskweave_api.ingestion.chunking import chunk_text
from riskweave_api.ingestion.models import (
    Base,
    DataSnapshot,
    Document,
    MacroObservation,
    SnapshotMember,
    XbrlFact,
)
from riskweave_api.ingestion.rate_limit import RateLimiter
from riskweave_api.ingestion.repository import Repository, SnapshotImmutableError
from riskweave_api.ingestion.service import IngestionService


def test_chunks_reconstruct_original_passages() -> None:
    text = ("alpha beta gamma\n\n" * 2000).strip()
    chunks = chunk_text(text, target_size=500, overlap=50, hard_max_size=600)
    assert chunks
    assert all(chunk.text == text[chunk.char_start : chunk.char_end] for chunk in chunks)
    assert all(len(chunk.text) <= 600 for chunk in chunks)


def test_rate_limiter_caps_requests_with_mock_clock() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(10, clock=lambda: now[0], sleep=sleep)
    for _ in range(11):
        limiter.acquire()
    assert now[0] == pytest.approx(1.0)
    assert sum(sleeps) == pytest.approx(1.0)


def test_repository_is_idempotent_and_rejects_hash_conflict() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = Repository(session)
        values = dict(
            source_document_id="0001-24-000001",
            cik="0000000001",
            accession_number="0001-24-000001",
            form="10-K",
            filing_date=date(2024, 1, 1),
            source_url="https://www.sec.gov/Archives/example.htm",
            retrieved_at=datetime.now(UTC),
            content_hash="abc",
            canonical_text="hello",
        )
        first = repository.upsert_document(**values)
        second = repository.upsert_document(**values)
        assert first.id == second.id
        with pytest.raises(ValueError, match="content hash conflict"):
            repository.upsert_document(**(values | {"content_hash": "changed"}))


def test_snapshot_is_immutable() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        snapshot = DataSnapshot(name="demo", manifest_hash="hash", frozen_at=datetime.now(UTC))
        session.add(snapshot)
        session.flush()
        session.add(
            SnapshotMember(
                snapshot_id=snapshot.id,
                record_type="document",
                record_id="1",
                content_hash="abc",
            )
        )
        session.commit()
        repository = Repository(session)
        with pytest.raises(SnapshotImmutableError):
            repository.add_snapshot_member(snapshot.id, "document", "2", "def")
        assert session.scalar(select(DataSnapshot).where(DataSnapshot.name == "demo"))


class _FakeFred:
    def __init__(self, realtime: str = "2026-07-11") -> None:
        self.realtime = realtime

    def usage_stats(self) -> dict:
        return {"provider": "fred", "request_count": 0, "rate_limit_requests_per_minute": 120}

    def series(self, series_id: str) -> dict:
        return {
            "seriess": [
                {
                    "id": series_id,
                    "title": "Test series",
                    "units": "Index",
                    "frequency": "Daily",
                    "notes": "Test release",
                }
            ]
        }

    def observations(self, series_id: str) -> dict:
        return {
            "observations": [
                {
                    "date": "2024-01-01",
                    "value": ".",
                    "realtime_start": self.realtime,
                    "realtime_end": self.realtime,
                },
                {
                    "date": "2024-01-02",
                    "value": "12.5",
                    "realtime_start": self.realtime,
                    "realtime_end": self.realtime,
                },
            ]
        }


def test_fred_skips_missing_values_and_ignores_request_time_envelope() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = IngestionService(session, object(), _FakeFred())  # type: ignore[arg-type]
        first = service._ingest_fred("TEST")
        session.flush()
        service.fred = _FakeFred("2026-07-12")  # type: ignore[assignment]
        second = service._ingest_fred("TEST")
        assert first == second
        assert [member[0] for member in first] == ["macro_series", "macro_observation"]


class _FakeSec:
    def usage_stats(self) -> dict:
        return {
            "provider": "sec_edgar",
            "user_agent": "RiskWeave test@example.com",
            "request_count": 0,
            "fair_use_requests_per_second": 10,
        }

    def submissions(self, cik: str) -> dict:
        accessions = [f"{int(cik):010d}-24-{index:06d}" for index in range(1, 4)]
        return {
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "8-K"],
                    "accessionNumber": accessions,
                    "primaryDocument": ["filing.htm"] * 3,
                    "filingDate": ["2024-01-01", "2024-04-01", "2024-07-01"],
                    "reportDate": ["2023-12-31", "2024-03-31", "2024-06-30"],
                },
                "files": [],
            }
        }

    def submissions_file(self, name: str) -> dict:
        return {}

    def filing(self, cik: str, accession: str, primary_document: str) -> tuple[str, str]:
        return (
            f"https://www.sec.gov/Archives/{accession}/{primary_document}",
            f"<html><body><p>Filing {accession} for {cik}</p></body></html>",
        )

    def companyfacts(self, cik: str) -> dict:
        accession = f"{int(cik):010d}-24-000001"
        return {
            "facts": {
                "us-gaap": {
                    "Assets": {
                        "units": {
                            "USD": [
                                {
                                    "val": 100,
                                    "end": "2023-12-31",
                                    "accn": accession,
                                    "form": "10-K",
                                    "filed": "2024-01-01",
                                    "fy": 2023,
                                    "fp": "FY",
                                }
                            ]
                        }
                    }
                }
            }
        }


def test_full_universe_second_run_is_provider_data_noop() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    universe = Path(__file__).resolve().parents[2] / "data/universe/entities.json"
    with Session(engine) as session:
        first = IngestionService(session, _FakeSec(), _FakeFred()).run(universe, "fixture")
        counts = (
            session.query(Document).count(),
            session.query(XbrlFact).count(),
            session.query(MacroObservation).count(),
        )
        second = IngestionService(session, _FakeSec(), _FakeFred()).run(universe, "fixture")
        assert second == first
        assert (
            session.query(Document).count(),
            session.query(XbrlFact).count(),
            session.query(MacroObservation).count(),
        ) == counts

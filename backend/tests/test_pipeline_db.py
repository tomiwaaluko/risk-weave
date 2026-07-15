"""Tests for the DB-backed live assembly path (RIS-28).

Exercises ``assemble_live_from_db`` end-to-end against a real (SQLite) database
seeded with documents + relationship extractions, proving the live graph is
built from stored extraction rows — the durable serving path Railway uses when a
one-off extraction job's filesystem is ephemeral.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from riskweave.graph.build_live import SnapshotNotFoundError, assemble_live_from_db
from riskweave_api.ingestion.models import (
    Base,
    DataSnapshot,
    Document,
    DocumentChunk,
    RelationshipExtraction,
)

_UNIVERSE = {
    "entities": [
        {
            "id": "reit:bxp",
            "canonical_name": "Boston Properties",
            "entity_type": "reit",
            "packs": ["cre"],
            "ticker": "BXP",
        },
        {
            "id": "bank:wfc",
            "canonical_name": "Wells Fargo",
            "entity_type": "bank",
            "packs": ["cre"],
            "ticker": "WFC",
        },
    ]
}


@pytest.fixture
def universe_file(tmp_path: Path) -> Path:
    path = tmp_path / "entities.json"
    path.write_text(json.dumps(_UNIVERSE), encoding="utf-8")
    return path


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def _seed(session: Session) -> None:
    snapshot = DataSnapshot(id=3, name="demo-2026-07-12", manifest_hash="hash-3", manifest_json={})
    doc = Document(
        id=1,
        source_document_id="0000038777-24-000012",
        cik="0000038777",
        accession_number="0000038777-24-000012",
        form="10-K",
        filing_date=date(2024, 2, 27),
        source_url="https://sec.gov/x",
        retrieved_at=datetime.now(UTC),
        content_hash="h",
        canonical_text="...",
        provider_metadata={},
        normalization_map={},
    )
    chunk = DocumentChunk(
        id=1, document_id=1, ordinal=0, text="...", char_start=0, char_end=3, content_hash="c"
    )
    passage = "approximately 28% of the loan portfolio"
    rel = RelationshipExtraction(
        id=1,
        snapshot_id=3,
        chunk_id=1,
        source_entity="WFC",
        target_entity="BXP",
        relationship_type="creditor",
        direction="positive",
        disclosed_magnitude="approximately 28% of the loan portfolio",
        source_passage=passage,
        source_document_id="0000038777-24-000012",
        char_start=100,
        char_end=100 + len(passage),
        extraction_confidence=0.9,
        content_hash="rel-hash-1",
        validated_at=datetime.now(UTC),
    )
    session.add_all([snapshot, doc, chunk, rel])
    session.commit()


class TestAssembleFromDb:
    def test_builds_live_graph_from_stored_extractions(
        self, session: Session, universe_file: Path
    ) -> None:
        _seed(session)
        result, snapshot = assemble_live_from_db(
            session, snapshot_id=3, universe_path=universe_file, graph_version="live-1.0.0"
        )
        assert snapshot.name == "demo-2026-07-12"
        assert result.graph.snapshot_id == "demo-2026-07-12"
        assert len(result.graph.edges) == 1
        edge = result.graph.edges[0]
        assert (edge.source_id, edge.target_id) == ("bank:wfc", "reit:bxp")
        assert edge.record.value == pytest.approx(0.28)
        # Provenance is complete on the generated edge (RW-ALG-032).
        assert result.graph.provenance_coverage() == 1.0

    def test_missing_snapshot_raises(self, session: Session, universe_file: Path) -> None:
        with pytest.raises(SnapshotNotFoundError):
            assemble_live_from_db(session, snapshot_id=999, universe_path=universe_file)

    def test_empty_extractions_yield_empty_graph(
        self, session: Session, universe_file: Path
    ) -> None:
        session.add(DataSnapshot(id=3, name="empty", manifest_hash="h", manifest_json={}))
        session.commit()
        result, _ = assemble_live_from_db(session, snapshot_id=3, universe_path=universe_file)
        assert result.graph.edges == ()
        assert result.default_factors == ()

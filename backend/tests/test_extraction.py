from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from riskweave_api.extraction.gemini import (
    GEMINI_EXTRACTION_MODEL,
    GeminiExtractionClient,
    GeminiResponseError,
    GeminiRestTransport,
)
from riskweave_api.extraction.schemas import (
    CovenantThresholdExtractionBatch,
    RelationshipExtractionBatch,
    covenant_response_schema,
    relationship_response_schema,
)
from riskweave_api.extraction.service import ExtractionService, OffsetMismatchError
from riskweave_api.ingestion.models import (
    Base,
    DataSnapshot,
    Document,
    DocumentChunk,
    ExtractionRun,
    RelationshipExtraction,
    SnapshotMember,
)
from riskweave_api.settings import Settings


@contextmanager
def _session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, connection_record: object) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
        char_start=100,
        char_end=100 + len(document.canonical_text),
        overlap_start=None,
        overlap_end=None,
        content_hash="chunk-hash",
    )
    document.chunks.append(chunk)
    snapshot = DataSnapshot(
        name="fixture",
        manifest_hash="snapshot-hash",
        frozen_at=datetime.now(UTC),
        manifest_json={"members": [["document", document.accession_number, document.content_hash]]},
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


def test_schema_has_no_estimated_sensitivity_field() -> None:
    schema = relationship_response_schema()
    serialized = str(schema)
    assert "estimated_sensitivity" not in serialized
    with pytest.raises(ValidationError):
        RelationshipExtractionBatch.model_validate(
            {
                "relationships": [
                    {
                        "source_entity": "Acme",
                        "target_entity": "Beta",
                        "relationship_type": "credit",
                        "direction": "positive",
                        "disclosed_magnitude": "$50 million",
                        "source_passage": "Acme lends to Beta",
                        "passage_location": {
                            "source_document_id": "0000000001-24-000001",
                            "char_start": 0,
                            "char_end": 18,
                        },
                        "extraction_confidence": 0.9,
                        "estimated_sensitivity": 0.7,
                    }
                ]
            }
        )


def test_top_level_extraction_arrays_are_required() -> None:
    assert "relationships" in relationship_response_schema()["required"]
    assert "covenants" in covenant_response_schema()["required"]
    with pytest.raises(ValidationError):
        RelationshipExtractionBatch.model_validate({})
    with pytest.raises(ValidationError):
        CovenantThresholdExtractionBatch.model_validate({})


def test_rejects_empty_passage_and_zero_length_offsets() -> None:
    with pytest.raises(ValidationError):
        RelationshipExtractionBatch.model_validate(
            {
                "relationships": [
                    {
                        "source_entity": "Acme",
                        "target_entity": "Beta",
                        "relationship_type": "credit",
                        "direction": "positive",
                        "disclosed_magnitude": "$50 million",
                        "source_passage": "",
                        "passage_location": {
                            "source_document_id": "0000000001-24-000001",
                            "char_start": 0,
                            "char_end": 0,
                        },
                        "extraction_confidence": 0.9,
                    }
                ]
            }
        )


def test_rejects_extraction_with_mismatched_offsets() -> None:
    with _session() as session:
        snapshot, chunk = _seed_snapshot(session)
        service = ExtractionService(session)
        with pytest.raises(OffsetMismatchError):
            service.store_relationships(
                snapshot_id=snapshot.id,
                chunk_id=chunk.id,
                run_id=None,
                payload=RelationshipExtractionBatch.model_validate(
                    {
                        "relationships": [
                            {
                                "source_entity": "Acme",
                                "target_entity": "Beta",
                                "relationship_type": "credit",
                                "direction": "positive",
                                "disclosed_magnitude": "$50 million",
                                "source_passage": "Acme lends to Beta",
                                "passage_location": {
                                    "source_document_id": "0000000001-24-000001",
                                    "char_start": 1,
                                    "char_end": 19,
                                },
                                "extraction_confidence": 0.9,
                            }
                        ]
                    }
                ),
            )


class _FlakyTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_interaction(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {"output_text": '{"relationships": [{"source_entity": "Acme"}]}'}
        if "No disclosed relationships here." in str(kwargs.get("input")):
            return {"output_text": '{"relationships": []}'}
        return {
            "output_text": """
            {
              "relationships": [{
                "source_entity": "Acme",
                "target_entity": "Beta",
                "relationship_type": "credit",
                "direction": "positive",
                "disclosed_magnitude": "$50 million",
                "source_passage": "Acme lends to Beta",
                "passage_location": {
                  "source_document_id": "0000000001-24-000001",
                  "char_start": 0,
                  "char_end": 18
                },
                "extraction_confidence": 0.91
              }]
            }
            """,
            "usage": {"input_tokens": 11, "output_tokens": 29},
        }


def test_bounded_retry_logs_schema_validity_outcome() -> None:
    with _session() as session:
        snapshot, chunk = _seed_snapshot(session)
        transport = _FlakyTransport()
        client = GeminiExtractionClient(transport, api_key=SecretStr("server-only"))
        service = ExtractionService(session, client=client)
        result = service.extract_relationships_for_chunk(snapshot.id, chunk.id)
        assert result.inserted == 1
        assert len(transport.calls) == 2
        first_call = transport.calls[0]
        assert first_call["model"] == GEMINI_EXTRACTION_MODEL
        assert first_call["temperature"] == 0
        assert first_call["response_format"] == {
            "type": "text",
            "mime_type": "application/json",
            "schema": relationship_response_schema(),
        }
        run = session.scalar(select(ExtractionRun))
        assert run is not None
        assert run.status == "completed"
        assert run.attempts == 2
        assert run.input_token_count == 11
        assert run.output_token_count == 29
        assert run.outcome_json["schema_valid_after_retry"] is True


def test_pipeline_resume_skips_existing_chunk_without_duplicate_rows() -> None:
    with _session() as session:
        snapshot, chunk = _seed_snapshot(session)
        service = ExtractionService(session, client=GeminiExtractionClient(_FlakyTransport()))
        first = service.extract_relationships_for_chunk(snapshot.id, chunk.id)
        second = service.extract_relationships_for_chunk(snapshot.id, chunk.id)
        assert first.inserted == 1
        assert second.skipped_existing is True
        assert session.query(RelationshipExtraction).count() == 1
        assert session.query(ExtractionRun).count() == 1


def test_snapshot_batch_processes_chunks_and_resumes_existing_runs() -> None:
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
        service = ExtractionService(session, client=GeminiExtractionClient(_FlakyTransport()))
        first = service.extract_relationships_for_snapshot(snapshot.id)
        second = service.extract_relationships_for_snapshot(snapshot.id)
        assert first.chunks_seen == 2
        assert first.inserted == 1
        assert second.skipped_existing == 2
        assert session.query(RelationshipExtraction).count() == 1


def test_distinct_same_passage_relationships_are_not_deduped() -> None:
    with _session() as session:
        snapshot, chunk = _seed_snapshot(session)
        payload = RelationshipExtractionBatch.model_validate(
            {
                "relationships": [
                    {
                        "source_entity": "Acme",
                        "target_entity": "Beta",
                        "relationship_type": "credit",
                        "direction": direction,
                        "disclosed_magnitude": magnitude,
                        "source_passage": "Acme lends to Beta",
                        "passage_location": {
                            "source_document_id": "0000000001-24-000001",
                            "char_start": 0,
                            "char_end": 18,
                        },
                        "extraction_confidence": 0.9,
                    }
                    for direction, magnitude in [
                        ("positive", "$50 million"),
                        ("negative", "$25 million"),
                    ]
                ]
            }
        )
        inserted = ExtractionService(session).store_relationships(
            snapshot_id=snapshot.id,
            chunk_id=chunk.id,
            run_id=None,
            payload=payload,
        )
        assert inserted == 2
        assert session.query(RelationshipExtraction).count() == 2


def test_covenant_schema_invalid_retry_is_logged() -> None:
    class AlwaysInvalid:
        def create_interaction(self, **kwargs: object) -> dict[str, object]:
            return {"output_text": '{"covenants": [{"entity": "Acme"}]}'}

    with _session() as session:
        snapshot, chunk = _seed_snapshot(session)
        service = ExtractionService(
            session,
            client=GeminiExtractionClient(AlwaysInvalid(), max_attempts=2),
        )
        with pytest.raises(GeminiResponseError):
            service.extract_covenants_for_chunk(snapshot.id, chunk.id)
        run = session.scalar(select(ExtractionRun))
        assert run is not None
        assert run.status == "schema_invalid"
        assert run.attempts == 2
        assert run.outcome_json["schema_valid_after_retry"] is False


def test_gemini_api_key_is_read_from_server_settings_only() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        neo4j_uri="bolt://neo4j:7687",
        neo4j_user="neo4j",
        neo4j_password="password",
        redis_url="redis://localhost:6379/0",
        gemini_api_key="real-server-side-key",
    )
    client = GeminiExtractionClient.from_settings(settings, transport=_FlakyTransport())
    assert client.api_key.get_secret_value() == "real-server-side-key"
    live_client = GeminiExtractionClient.from_settings(settings)
    assert isinstance(live_client.transport, GeminiRestTransport)


def test_rest_transport_normalizes_structured_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"relationships": []}).encode()

    def fake_urlopen(request: object, timeout: int) -> _Response:
        assert timeout == 60
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    response = GeminiRestTransport(SecretStr("server-only")).create_interaction(
        model=GEMINI_EXTRACTION_MODEL,
        input="prompt",
        temperature=0,
        response_format={},
    )
    assert response == {"output_text": '{"relationships": []}', "usage": {}}


def test_client_fails_after_bounded_schema_invalid_retries() -> None:
    class AlwaysInvalid:
        def create_interaction(self, **kwargs: object) -> dict[str, object]:
            return {"output_text": '{"relationships": [{"source_entity": "Acme"}]}'}

    client = GeminiExtractionClient(AlwaysInvalid(), max_attempts=2)
    with pytest.raises(GeminiResponseError):
        client.extract_relationships("text", "doc", 0)

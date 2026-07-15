from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from riskweave_api.accounting.service import BudgetExceededError, GeminiAccountingService
from riskweave_api.ingestion.models import (
    CovenantThresholdExtraction,
    Document,
    DocumentChunk,
    ExtractionRun,
    RelationshipExtraction,
    SnapshotMember,
)

from .gemini import (
    COVENANT_PROMPT_VERSION,
    GEMINI_DOCS_CHECKED_AT,
    GEMINI_EXTRACTION_MODEL,
    RELATIONSHIP_PROMPT_VERSION,
    GeminiExtractionClient,
    GeminiResponseError,
)
from .schemas import (
    CovenantThresholdExtractionBatch,
    RelationshipExtractionBatch,
)

logger = logging.getLogger("riskweave_api.extraction")


class OffsetMismatchError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractionResult:
    inserted: int
    skipped_existing: bool = False


@dataclass(frozen=True)
class BatchExtractionResult:
    chunks_seen: int
    inserted: int
    skipped_existing: int


class ExtractionService:
    def __init__(
        self,
        session: Session,
        client: GeminiExtractionClient | None = None,
        accounting: GeminiAccountingService | None = None,
    ) -> None:
        self.session = session
        self.client = client
        self.accounting = accounting

    def extract_relationships_for_chunk(self, snapshot_id: int, chunk_id: int) -> ExtractionResult:
        run = self._get_or_create_run(
            snapshot_id=snapshot_id,
            chunk_id=chunk_id,
            schema_name="relationship-extraction-v1",
            prompt_version=RELATIONSHIP_PROMPT_VERSION,
        )
        if run.status == "completed":
            return ExtractionResult(inserted=0, skipped_existing=True)
        if self.client is None:
            raise RuntimeError("Gemini client is required for extraction")
        # RIS-34 / RW-AI-003: refuse to start further extraction calls once the
        # hard daily budget is hit; the run stays "running" so a later
        # invocation resumes it (`_get_or_create_run` only skips "completed"
        # runs).
        if self.accounting is not None:
            self.accounting.check_budget_or_raise(self.session, purpose="extraction")
        chunk = self._chunk(chunk_id)
        document = self._document(chunk)
        try:
            response = self.client.extract_relationships(
                chunk.text, document.source_document_id, chunk.ordinal
            )
            inserted = self.store_relationships(
                snapshot_id=snapshot_id,
                chunk_id=chunk_id,
                run_id=run.id,
                payload=response.payload,
            )
        except GeminiResponseError as exc:
            self._mark_schema_invalid(run, exc)
            raise
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.attempts = response.attempts
        run.input_token_count = response.input_token_count
        run.output_token_count = response.output_token_count
        run.outcome_json = {
            "inserted": inserted,
            "retry_failures": response.retry_failures,
            "schema_valid_after_retry": bool(response.retry_failures),
        }
        self.session.flush()
        if self.accounting is not None:
            self.accounting.record(
                self.session,
                purpose="extraction",
                model=GEMINI_EXTRACTION_MODEL,
                input_tokens=response.input_token_count,
                output_tokens=response.output_token_count,
            )
        return ExtractionResult(inserted=inserted)

    def extract_relationships_for_snapshot(self, snapshot_id: int) -> BatchExtractionResult:
        chunk_ids = self._snapshot_chunk_ids(snapshot_id)
        inserted = 0
        skipped_existing = 0
        for chunk_id in chunk_ids:
            try:
                result = self.extract_relationships_for_chunk(snapshot_id, chunk_id)
            except BudgetExceededError as exc:
                # Halt gracefully so the caller can commit the chunks already
                # completed above; the next invocation resumes at this chunk
                # (`_get_or_create_run` only skips "completed" runs).
                logger.warning("relationship extraction batch paused: %s", exc)
                break
            inserted += result.inserted
            skipped_existing += int(result.skipped_existing)
        return BatchExtractionResult(
            chunks_seen=len(chunk_ids),
            inserted=inserted,
            skipped_existing=skipped_existing,
        )

    def extract_covenants_for_chunk(self, snapshot_id: int, chunk_id: int) -> ExtractionResult:
        run = self._get_or_create_run(
            snapshot_id=snapshot_id,
            chunk_id=chunk_id,
            schema_name="covenant-threshold-extraction-v1",
            prompt_version=COVENANT_PROMPT_VERSION,
        )
        if run.status == "completed":
            return ExtractionResult(inserted=0, skipped_existing=True)
        if self.client is None:
            raise RuntimeError("Gemini client is required for extraction")
        if self.accounting is not None:
            self.accounting.check_budget_or_raise(self.session, purpose="extraction")
        chunk = self._chunk(chunk_id)
        document = self._document(chunk)
        try:
            response = self.client.extract_covenants(
                chunk.text, document.source_document_id, chunk.ordinal
            )
            inserted = self.store_covenants(
                snapshot_id=snapshot_id,
                chunk_id=chunk_id,
                run_id=run.id,
                payload=response.payload,
            )
        except GeminiResponseError as exc:
            self._mark_schema_invalid(run, exc)
            raise
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.attempts = response.attempts
        run.input_token_count = response.input_token_count
        run.output_token_count = response.output_token_count
        run.outcome_json = {"inserted": inserted, "retry_failures": response.retry_failures}
        self.session.flush()
        if self.accounting is not None:
            self.accounting.record(
                self.session,
                purpose="extraction",
                model=GEMINI_EXTRACTION_MODEL,
                input_tokens=response.input_token_count,
                output_tokens=response.output_token_count,
            )
        return ExtractionResult(inserted=inserted)

    def extract_covenants_for_snapshot(self, snapshot_id: int) -> BatchExtractionResult:
        chunk_ids = self._snapshot_chunk_ids(snapshot_id)
        inserted = 0
        skipped_existing = 0
        for chunk_id in chunk_ids:
            try:
                result = self.extract_covenants_for_chunk(snapshot_id, chunk_id)
            except BudgetExceededError as exc:
                logger.warning("covenant extraction batch paused: %s", exc)
                break
            inserted += result.inserted
            skipped_existing += int(result.skipped_existing)
        return BatchExtractionResult(
            chunks_seen=len(chunk_ids),
            inserted=inserted,
            skipped_existing=skipped_existing,
        )

    def store_relationships(
        self,
        *,
        snapshot_id: int,
        chunk_id: int,
        run_id: int | None,
        payload: RelationshipExtractionBatch,
    ) -> int:
        chunk = self._chunk(chunk_id)
        document = self._document(chunk)
        inserted = 0
        for item in payload.relationships:
            absolute_start, absolute_end = self._validate_passage(
                document.source_document_id,
                chunk,
                item.passage_location.source_document_id,
                item.passage_location.char_start,
                item.passage_location.char_end,
                item.source_passage,
            )
            content_hash = _hash(
                {
                    "snapshot_id": snapshot_id,
                    "source_document_id": document.source_document_id,
                    "char_start": absolute_start,
                    "char_end": absolute_end,
                    "source_entity": item.source_entity,
                    "target_entity": item.target_entity,
                    "relationship_type": item.relationship_type,
                    "direction": item.direction,
                    "disclosed_magnitude": item.disclosed_magnitude,
                }
            )
            existing = self.session.scalar(
                select(RelationshipExtraction).where(
                    RelationshipExtraction.content_hash == content_hash
                )
            )
            if existing:
                continue
            self.session.add(
                RelationshipExtraction(
                    snapshot_id=snapshot_id,
                    chunk_id=chunk_id,
                    extraction_run_id=run_id,
                    source_entity=item.source_entity,
                    target_entity=item.target_entity,
                    relationship_type=item.relationship_type,
                    direction=item.direction,
                    disclosed_magnitude=item.disclosed_magnitude,
                    source_passage=item.source_passage,
                    source_document_id=document.source_document_id,
                    char_start=absolute_start,
                    char_end=absolute_end,
                    extraction_confidence=item.extraction_confidence,
                    content_hash=content_hash,
                    validated_at=datetime.now(UTC),
                )
            )
            inserted += 1
        self.session.flush()
        return inserted

    def store_covenants(
        self,
        *,
        snapshot_id: int,
        chunk_id: int,
        run_id: int | None,
        payload: CovenantThresholdExtractionBatch,
    ) -> int:
        chunk = self._chunk(chunk_id)
        document = self._document(chunk)
        inserted = 0
        for item in payload.covenants:
            absolute_start, absolute_end = self._validate_passage(
                document.source_document_id,
                chunk,
                item.passage_location.source_document_id,
                item.passage_location.char_start,
                item.passage_location.char_end,
                item.source_passage,
            )
            content_hash = _hash(
                {
                    "snapshot_id": snapshot_id,
                    "source_document_id": document.source_document_id,
                    "char_start": absolute_start,
                    "char_end": absolute_end,
                    "entity": item.entity,
                    "covenant_type": item.covenant_type,
                    "threshold_value": item.threshold_value,
                }
            )
            existing = self.session.scalar(
                select(CovenantThresholdExtraction).where(
                    CovenantThresholdExtraction.content_hash == content_hash
                )
            )
            if existing:
                continue
            self.session.add(
                CovenantThresholdExtraction(
                    snapshot_id=snapshot_id,
                    chunk_id=chunk_id,
                    extraction_run_id=run_id,
                    entity=item.entity,
                    covenant_type=item.covenant_type,
                    threshold_value=item.threshold_value,
                    source_passage=item.source_passage,
                    source_document_id=document.source_document_id,
                    char_start=absolute_start,
                    char_end=absolute_end,
                    extraction_confidence=item.extraction_confidence,
                    content_hash=content_hash,
                    validated_at=datetime.now(UTC),
                )
            )
            inserted += 1
        self.session.flush()
        return inserted

    def _get_or_create_run(
        self, *, snapshot_id: int, chunk_id: int, schema_name: str, prompt_version: str
    ) -> ExtractionRun:
        existing = self.session.scalar(
            select(ExtractionRun).where(
                ExtractionRun.snapshot_id == snapshot_id,
                ExtractionRun.chunk_id == chunk_id,
                ExtractionRun.schema_name == schema_name,
                ExtractionRun.prompt_version == prompt_version,
                ExtractionRun.model == GEMINI_EXTRACTION_MODEL,
            )
        )
        if existing:
            return existing
        run = ExtractionRun(
            snapshot_id=snapshot_id,
            chunk_id=chunk_id,
            schema_name=schema_name,
            prompt_version=prompt_version,
            model=GEMINI_EXTRACTION_MODEL,
            model_docs_checked_at=GEMINI_DOCS_CHECKED_AT,
            status="running",
            attempts=0,
            outcome_json={},
            started_at=datetime.now(UTC),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def _validate_passage(
        self,
        expected_source_document_id: str,
        chunk: DocumentChunk,
        claimed_source_document_id: str,
        local_start: int,
        local_end: int,
        source_passage: str,
    ) -> tuple[int, int]:
        if claimed_source_document_id != expected_source_document_id:
            raise OffsetMismatchError("source document id does not match chunk document")
        if local_end <= local_start or local_end > len(chunk.text):
            raise OffsetMismatchError("passage offsets are outside the chunk")
        actual = chunk.text[local_start:local_end]
        if actual != source_passage:
            raise OffsetMismatchError("source passage does not match claimed offsets")
        return chunk.char_start + local_start, chunk.char_start + local_end

    def _mark_schema_invalid(self, run: ExtractionRun, exc: GeminiResponseError) -> None:
        run.status = "schema_invalid"
        run.completed_at = datetime.now(UTC)
        run.attempts = exc.attempts
        run.outcome_json = {"failures": exc.failures, "schema_valid_after_retry": False}
        self.session.flush()

    def _chunk(self, chunk_id: int) -> DocumentChunk:
        chunk = self.session.get(DocumentChunk, chunk_id)
        if chunk is None:
            raise LookupError("document chunk not found")
        return chunk

    def _document(self, chunk: DocumentChunk) -> Document:
        document = self.session.get(Document, chunk.document_id)
        if document is None:
            raise LookupError("document not found")
        return document

    def _snapshot_chunk_ids(self, snapshot_id: int) -> list[int]:
        rows = self.session.execute(
            select(DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.accession_number.in_(
                    select(SnapshotMember.record_id).where(
                        SnapshotMember.snapshot_id == snapshot_id,
                        SnapshotMember.record_type == "document",
                    )
                )
            )
            .order_by(Document.accession_number, DocumentChunk.ordinal)
        )
        return [row[0] for row in rows]


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()

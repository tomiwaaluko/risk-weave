"""Load extracted relationships from Postgres for live graph assembly (RIS-28)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from riskweave.graph.live import ExtractedRelationshipInput, LiveAssemblyError
from riskweave_api.ingestion.models import Document, RelationshipExtraction


def load_extracted_relationships(
    session: Session,
    snapshot_id: int,
) -> list[ExtractedRelationshipInput]:
    """Return already-persisted extraction rows for ``snapshot_id``.

    Joins documents for filing dates. Does **not** call Gemini.
    """
    rows = session.execute(
        select(RelationshipExtraction, Document.filing_date)
        .join(
            Document,
            Document.source_document_id == RelationshipExtraction.source_document_id,
        )
        .where(RelationshipExtraction.snapshot_id == snapshot_id)
        .order_by(RelationshipExtraction.id)
    ).all()

    if not rows:
        raise LiveAssemblyError(
            f"no extracted relationships for snapshot_id={snapshot_id}; "
            "run extraction over the snapshot first "
            "(uv run python -m riskweave.graph.assemble_live --help), "
            "or POST /graph/seed with source=fixture"
        )

    out: list[ExtractedRelationshipInput] = []
    for rel, filing_date in rows:
        # Disclosure as-of is the filing date; Gemini does not invent timestamps.
        data_ts = datetime.combine(filing_date, datetime.min.time())
        direction = (rel.direction or "").strip().lower()
        if direction not in ("positive", "negative"):
            raise LiveAssemblyError(
                f"relationship_extractions.id={rel.id} has unsupported direction "
                f"{rel.direction!r}; refusing to guess an edge sign"
            )
        out.append(
            ExtractedRelationshipInput(
                source_entity=rel.source_entity,
                target_entity=rel.target_entity,
                relationship_type=rel.relationship_type,
                direction=direction,  # type: ignore[arg-type]
                disclosed_magnitude=rel.disclosed_magnitude,
                source_passage=rel.source_passage,
                source_document_id=rel.source_document_id,
                char_start=rel.char_start,
                char_end=rel.char_end,
                extraction_confidence=rel.extraction_confidence,
                filing_date=filing_date,
                data_timestamp=data_ts,
            )
        )
    return out

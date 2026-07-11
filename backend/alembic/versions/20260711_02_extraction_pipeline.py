"""RIS-10 Gemini extraction schema."""

import sqlalchemy as sa

from alembic import op

revision = "20260711_02"
down_revision = "20260711_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("data_snapshots.id"), nullable=False),
        sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id"), nullable=False),
        sa.Column("schema_name", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("model_docs_checked_at", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("input_token_count", sa.Integer()),
        sa.Column("output_token_count", sa.Integer()),
        sa.Column("outcome_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("snapshot_id", "chunk_id", "schema_name", "prompt_version", "model"),
    )
    op.create_table(
        "relationship_extractions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("data_snapshots.id"), nullable=False),
        sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id"), nullable=False),
        sa.Column("extraction_run_id", sa.Integer(), sa.ForeignKey("extraction_runs.id")),
        sa.Column("source_entity", sa.Text(), nullable=False),
        sa.Column("target_entity", sa.Text(), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("disclosed_magnitude", sa.Text()),
        sa.Column("source_passage", sa.Text(), nullable=False),
        sa.Column("source_document_id", sa.String(64), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "covenant_threshold_extractions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("data_snapshots.id"), nullable=False),
        sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id"), nullable=False),
        sa.Column("extraction_run_id", sa.Integer(), sa.ForeignKey("extraction_runs.id")),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("covenant_type", sa.String(64), nullable=False),
        sa.Column("threshold_value", sa.Text(), nullable=False),
        sa.Column("source_passage", sa.Text(), nullable=False),
        sa.Column("source_document_id", sa.String(64), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("covenant_threshold_extractions")
    op.drop_table("relationship_extractions")
    op.drop_table("extraction_runs")

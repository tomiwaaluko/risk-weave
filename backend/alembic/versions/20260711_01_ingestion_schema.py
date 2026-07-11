"""RIS-8 ingestion schema and immutable snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "20260711_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_document_id", sa.String(64), nullable=False, unique=True),
        sa.Column("cik", sa.String(10), nullable=False),
        sa.Column("accession_number", sa.String(32), nullable=False, unique=True),
        sa.Column("form", sa.String(16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("provider_metadata", sa.JSON(), nullable=False),
        sa.Column("normalization_map", sa.JSON(), nullable=False),
    )
    op.create_index("ix_documents_cik", "documents", ["cik"])
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("overlap_start", sa.Integer()),
        sa.Column("overlap_end", sa.Integer()),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("document_id", "char_start", "char_end"),
    )
    op.create_table(
        "xbrl_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("cik", sa.String(10), nullable=False),
        sa.Column("taxonomy", sa.String(64), nullable=False),
        sa.Column("concept", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("accession_number", sa.String(32), nullable=False),
        sa.Column("form", sa.String(16), nullable=False),
        sa.Column("filed_date", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.Integer()),
        sa.Column("fiscal_period", sa.String(16)),
        sa.Column("frame", sa.String(64)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_xbrl_facts_cik", "xbrl_facts", ["cik"])
    op.create_table(
        "macro_series",
        sa.Column("series_id", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("units", sa.String(128), nullable=False),
        sa.Column("frequency", sa.String(128), nullable=False),
        sa.Column("source_release", sa.Text()),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
    )
    op.create_table(
        "macro_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "series_id", sa.String(64), sa.ForeignKey("macro_series.series_id"), nullable=False
        ),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric()),
        sa.Column("realtime_start", sa.Date(), nullable=False),
        sa.Column("realtime_end", sa.Date(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("series_id", "observation_date"),
    )
    op.create_table(
        "data_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("manifest_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True)),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "snapshot_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("data_snapshots.id"), nullable=False),
        sa.Column("record_type", sa.String(32), nullable=False),
        sa.Column("record_id", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("snapshot_id", "record_type", "record_id"),
    )
    if bind.dialect.name != "postgresql":
        return
    op.execute("""
    CREATE FUNCTION riskweave_reject_frozen_snapshot_member() RETURNS trigger AS $$
    BEGIN
      IF (TG_OP IN ('UPDATE', 'DELETE') AND EXISTS (
            SELECT 1 FROM data_snapshots WHERE id = OLD.snapshot_id AND frozen_at IS NOT NULL
          )) OR (TG_OP IN ('INSERT', 'UPDATE') AND EXISTS (
            SELECT 1 FROM data_snapshots WHERE id = NEW.snapshot_id AND frozen_at IS NOT NULL
          )) THEN
        RAISE EXCEPTION 'snapshot is immutable';
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER snapshot_members_immutable BEFORE INSERT OR UPDATE OR DELETE ON snapshot_members
      FOR EACH ROW EXECUTE FUNCTION riskweave_reject_frozen_snapshot_member();
    CREATE FUNCTION riskweave_reject_frozen_snapshot_change() RETURNS trigger AS $$
    BEGIN
      IF OLD.frozen_at IS NOT NULL THEN RAISE EXCEPTION 'snapshot is immutable'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER data_snapshots_immutable BEFORE UPDATE OR DELETE ON data_snapshots
      FOR EACH ROW EXECUTE FUNCTION riskweave_reject_frozen_snapshot_change();
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS snapshot_members_immutable ON snapshot_members")
        op.execute("DROP FUNCTION IF EXISTS riskweave_reject_frozen_snapshot_member")
        op.execute("DROP TRIGGER IF EXISTS data_snapshots_immutable ON data_snapshots")
        op.execute("DROP FUNCTION IF EXISTS riskweave_reject_frozen_snapshot_change")
    op.drop_table("snapshot_members")
    op.drop_table("data_snapshots")
    op.drop_table("macro_observations")
    op.drop_table("macro_series")
    op.drop_index("ix_xbrl_facts_cik", table_name="xbrl_facts")
    op.drop_table("xbrl_facts")
    op.drop_table("document_chunks")
    op.drop_index("ix_documents_cik", table_name="documents")
    op.drop_table("documents")
    op.drop_table("ingestion_runs")

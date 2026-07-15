"""RIS-34 provider cost/quota accounting: Gemini per-call usage records."""

import sqlalchemy as sa

from alembic import op

revision = "20260715_01"
down_revision = "20260714_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gemini_usage_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_gemini_usage_records_purpose", "gemini_usage_records", ["purpose"])
    op.create_index("ix_gemini_usage_records_created_at", "gemini_usage_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_gemini_usage_records_created_at", table_name="gemini_usage_records")
    op.drop_index("ix_gemini_usage_records_purpose", table_name="gemini_usage_records")
    op.drop_table("gemini_usage_records")

"""RIS-30 scenario, run, and graph snapshot persistence (+ RIS-19 Q&A session audit log)."""

import sqlalchemy as sa

from alembic import op

revision = "20260714_01"
down_revision = "20260711_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stored_graph_snapshots",
        sa.Column("snapshot_id", sa.String(128), primary_key=True),
        sa.Column("graph_version", sa.String(64), nullable=False),
        sa.Column("nodes_json", sa.JSON(), nullable=False),
        sa.Column("edges_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "stored_scenarios",
        sa.Column("scenario_id", sa.String(128), primary_key=True),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
        sa.Column("graph_version", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(32), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("factors_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "scenario_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "scenario_id",
            sa.String(128),
            sa.ForeignKey("stored_scenarios.scenario_id"),
            nullable=False,
        ),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
        sa.Column("graph_version", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(32), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scenario_runs_scenario_id", "scenario_runs", ["scenario_id"])
    op.create_table(
        "qa_sessions",
        sa.Column("session_id", sa.String(128), primary_key=True),
        sa.Column("answer_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("qa_sessions")
    op.drop_index("ix_scenario_runs_scenario_id", table_name="scenario_runs")
    op.drop_table("scenario_runs")
    op.drop_table("stored_scenarios")
    op.drop_table("stored_graph_snapshots")

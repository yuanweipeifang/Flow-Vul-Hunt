"""Add multi-agent collaboration trace tables.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "agent_runs" not in tables:
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("collaboration_mode", sa.String(length=64), nullable=False),
            sa.Column("runtime", sa.String(length=64), nullable=False),
            sa.Column("planner_used", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("max_parallelism", sa.Integer(), nullable=False),
            sa.Column("llm_used", sa.Boolean(), nullable=False),
            sa.Column("consensus", sa.JSON(), nullable=False),
            sa.Column("evidence_gaps", sa.JSON(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("session_id", "collaboration_mode", "runtime", "planner_used", "status", "llm_used"):
            op.create_index(f"ix_agent_runs_{column}", "agent_runs", [column])

    if "agent_messages" not in tables:
        op.create_table(
            "agent_messages",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("run_id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("agent_name", sa.String(length=64), nullable=False),
            sa.Column("role", sa.String(length=64), nullable=False),
            sa.Column("task", sa.Text(), nullable=False),
            sa.Column("input_summary", sa.JSON(), nullable=False),
            sa.Column("output", sa.JSON(), nullable=False),
            sa.Column("depends_on", sa.JSON(), nullable=False),
            sa.Column("evidence_refs", sa.JSON(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("llm_used", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("run_id", "session_id", "agent_name", "role", "llm_used", "status"):
            op.create_index(f"ix_agent_messages_{column}", "agent_messages", [column])


def downgrade() -> None:
    tables = _tables()
    if "agent_messages" in tables:
        op.drop_table("agent_messages")
    if "agent_runs" in tables:
        op.drop_table("agent_runs")

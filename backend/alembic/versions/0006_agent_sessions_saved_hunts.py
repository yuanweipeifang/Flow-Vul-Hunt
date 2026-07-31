"""Add agent sessions and saved hunt queries.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "agent_sessions" not in tables:
        op.create_table(
            "agent_sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("actor", sa.String(length=128), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("dataset_id", sa.String(length=36), nullable=True),
            sa.Column("runtime", sa.String(length=64), nullable=False),
            sa.Column("planner_used", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("plan", sa.JSON(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("warning", sa.Text(), nullable=True),
            sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("actor", "role", "dataset_id", "planner_used", "status", "requires_confirmation"):
            op.create_index(f"ix_agent_sessions_{column}", "agent_sessions", [column])

    if "agent_tool_calls" not in tables:
        op.create_table(
            "agent_tool_calls",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("call_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("risk_level", sa.String(length=32), nullable=False),
            sa.Column("arguments", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id", "call_id", name="uq_agent_tool_call"),
        )
        for column in ("session_id", "name", "risk_level", "status", "requires_confirmation"):
            op.create_index(f"ix_agent_tool_calls_{column}", "agent_tool_calls", [column])

    if "saved_hunt_queries" not in tables:
        op.create_table(
            "saved_hunt_queries",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("dataset_id", sa.String(length=36), nullable=True),
            sa.Column("filters", sa.JSON(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("created_by", sa.String(length=128), nullable=True),
            sa.Column("last_run_summary", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("name", "dataset_id", "created_by"):
            op.create_index(f"ix_saved_hunt_queries_{column}", "saved_hunt_queries", [column])


def downgrade() -> None:
    for table in ("saved_hunt_queries", "agent_tool_calls", "agent_sessions"):
        if table in _tables():
            op.drop_table(table)

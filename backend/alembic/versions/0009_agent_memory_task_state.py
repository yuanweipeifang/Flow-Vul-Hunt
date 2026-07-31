"""Add task graph, message protocol, and agent memory.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    tables = _tables()
    if "agent_sessions" in tables:
        columns = _columns("agent_sessions")
        if "task_graph" not in columns:
            op.add_column("agent_sessions", sa.Column("task_graph", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    if "agent_runs" in tables:
        columns = _columns("agent_runs")
        if "task_graph" not in columns:
            op.add_column("agent_runs", sa.Column("task_graph", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    if "agent_messages" in tables:
        columns = _columns("agent_messages")
        if "message_type" not in columns:
            op.add_column("agent_messages", sa.Column("message_type", sa.String(length=32), nullable=False, server_default="result"))
            op.create_index("ix_agent_messages_message_type", "agent_messages", ["message_type"])
        if "recipient" not in columns:
            op.add_column("agent_messages", sa.Column("recipient", sa.String(length=64), nullable=True))
            op.create_index("ix_agent_messages_recipient", "agent_messages", ["recipient"])
        if "follow_up_action" not in columns:
            op.add_column("agent_messages", sa.Column("follow_up_action", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        if "resolved" not in columns:
            op.add_column("agent_messages", sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("1")))
            op.create_index("ix_agent_messages_resolved", "agent_messages", ["resolved"])
    if "agent_memory" not in tables:
        op.create_table(
            "agent_memory",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("dataset_id", sa.String(length=36), nullable=True),
            sa.Column("agent_name", sa.String(length=64), nullable=False),
            sa.Column("memory_type", sa.String(length=32), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("content", sa.JSON(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("dataset_id", "agent_name", "memory_type", "created_at"):
            op.create_index(f"ix_agent_memory_{column}", "agent_memory", [column])


def downgrade() -> None:
    tables = _tables()
    if "agent_memory" in tables:
        op.drop_table("agent_memory")
    if "agent_messages" in tables:
        columns = _columns("agent_messages")
        for column in ("resolved", "follow_up_action", "recipient", "message_type"):
            if column in columns:
                op.drop_column("agent_messages", column)
    if "agent_runs" in tables and "task_graph" in _columns("agent_runs"):
        op.drop_column("agent_runs", "task_graph")
    if "agent_sessions" in tables and "task_graph" in _columns("agent_sessions"):
        op.drop_column("agent_sessions", "task_graph")

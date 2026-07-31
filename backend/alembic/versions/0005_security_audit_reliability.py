"""Add security, audit, and reliability fields.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    tables = _tables()
    if "analysis_jobs" in tables:
        columns = _columns("analysis_jobs")
        additions = [
            ("phase", sa.Column("phase", sa.String(length=64), nullable=False, server_default="queued")),
            ("current_event_id", sa.Column("current_event_id", sa.String(length=36), nullable=True)),
            ("last_heartbeat_at", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True)),
            ("last_error_at", sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True)),
            ("error_count", sa.Column("error_count", sa.Integer(), nullable=False, server_default="0")),
        ]
        for name, column in additions:
            if name not in columns:
                op.add_column("analysis_jobs", column)
        index_names = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("analysis_jobs")}
        for index_name, column_names in (
            ("ix_analysis_jobs_phase", ["phase"]),
            ("ix_analysis_jobs_current_event_id", ["current_event_id"]),
            ("ix_analysis_jobs_last_heartbeat_at", ["last_heartbeat_at"]),
        ):
            if index_name not in index_names:
                op.create_index(index_name, "analysis_jobs", column_names)

    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("actor", sa.String(length=128), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("resource_type", sa.String(length=64), nullable=False),
            sa.Column("resource_id", sa.String(length=128), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("action", "actor", "role", "request_id", "resource_type", "resource_id", "created_at"):
            op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])


def downgrade() -> None:
    if "audit_logs" in _tables():
        op.drop_table("audit_logs")

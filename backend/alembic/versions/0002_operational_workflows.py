"""Add operational workflow fields.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    job_columns = _columns("analysis_jobs")
    job_indexes = _indexes("analysis_jobs")
    with op.batch_alter_table("analysis_jobs") as batch:
        if "force" not in job_columns:
            batch.add_column(sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "cancel_requested" not in job_columns:
            batch.add_column(sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "updated_at" not in job_columns:
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )
        if "ix_analysis_jobs_cancel_requested" not in job_indexes:
            batch.create_index("ix_analysis_jobs_cancel_requested", ["cancel_requested"])

    incident_columns = _columns("incidents")
    incident_indexes = _indexes("incidents")
    with op.batch_alter_table("incidents") as batch:
        if "assignee" not in incident_columns:
            batch.add_column(sa.Column("assignee", sa.String(length=128), nullable=True))
        if "resolution" not in incident_columns:
            batch.add_column(sa.Column("resolution", sa.Text(), nullable=True))
        if "closed_at" not in incident_columns:
            batch.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
        if "ix_incidents_assignee" not in incident_indexes:
            batch.create_index("ix_incidents_assignee", ["assignee"])


def downgrade() -> None:
    incident_columns = _columns("incidents")
    incident_indexes = _indexes("incidents")
    with op.batch_alter_table("incidents") as batch:
        if "ix_incidents_assignee" in incident_indexes:
            batch.drop_index("ix_incidents_assignee")
        for column in ("closed_at", "resolution", "assignee"):
            if column in incident_columns:
                batch.drop_column(column)

    job_columns = _columns("analysis_jobs")
    job_indexes = _indexes("analysis_jobs")
    with op.batch_alter_table("analysis_jobs") as batch:
        if "ix_analysis_jobs_cancel_requested" in job_indexes:
            batch.drop_index("ix_analysis_jobs_cancel_requested")
        for column in ("updated_at", "cancel_requested", "force"):
            if column in job_columns:
                batch.drop_column(column)

"""Add stored CSV path to datasets.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if "storage_path" not in _columns("datasets"):
        op.add_column("datasets", sa.Column("storage_path", sa.Text(), nullable=True))


def downgrade() -> None:
    if "storage_path" in _columns("datasets"):
        op.drop_column("datasets", "storage_path")

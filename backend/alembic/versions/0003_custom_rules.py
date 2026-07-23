"""Add custom detection rules.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "custom_rules" in _tables():
        return
    op.create_table(
        "custom_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("attack_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_custom_rules_rule_id", "custom_rules", ["rule_id"], unique=True)
    op.create_index("ix_custom_rules_attack_type", "custom_rules", ["attack_type"])
    op.create_index("ix_custom_rules_severity", "custom_rules", ["severity"])
    op.create_index("ix_custom_rules_enabled", "custom_rules", ["enabled"])


def downgrade() -> None:
    if "custom_rules" in _tables():
        op.drop_table("custom_rules")

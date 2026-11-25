"""pricing: urgency scores and template discounts

Revision ID: 3959d7c69af7
Revises: 6afec7b572ec
Create Date: 2026-11-25 14:47:33.823385

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3959d7c69af7"
down_revision: str | None = "6afec7b572ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "urgency_scores",
        sa.Column("flower_type_id", sa.Integer(), nullable=False),
        sa.Column("expiring_qty", sa.Integer(), nullable=False),
        sa.Column("expected_demand", sa.Float(), nullable=False),
        sa.Column("surplus", sa.Integer(), nullable=False),
        sa.Column("min_days_left", sa.Float(), nullable=True),
        sa.Column("avg_freshness", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("discount_pct", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["flower_type_id"],
            ["flower_types.id"],
            name=op.f("fk_urgency_scores_flower_type_id_flower_types"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("flower_type_id", name=op.f("pk_urgency_scores")),
    )
    op.create_table(
        "template_discount_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("old_pct", sa.Integer(), nullable=False),
        sa.Column("new_pct", sa.Integer(), nullable=False),
        sa.Column("reason", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["bouquet_templates.id"],
            name=op.f("fk_template_discount_log_template_id_bouquet_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_discount_log")),
    )
    op.create_index(
        op.f("ix_template_discount_log_template_id"),
        "template_discount_log",
        ["template_id"],
        unique=False,
    )
    op.create_table(
        "template_discounts",
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("current_pct", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "current_pct BETWEEN 0 AND 90", name=op.f("ck_template_discounts_pct_range")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["bouquet_templates.id"],
            name=op.f("fk_template_discounts_template_id_bouquet_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("template_id", name=op.f("pk_template_discounts")),
    )


def downgrade() -> None:
    op.drop_table("template_discounts")
    op.drop_index(op.f("ix_template_discount_log_template_id"), table_name="template_discount_log")
    op.drop_table("template_discount_log")
    op.drop_table("urgency_scores")

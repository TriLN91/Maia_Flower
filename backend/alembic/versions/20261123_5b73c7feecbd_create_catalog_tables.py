"""create catalog tables

Revision ID: 5b73c7feecbd
Revises: 59babae2f8e8
Create Date: 2026-11-23 12:52:16.129569

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5b73c7feecbd"
down_revision: str | None = "59babae2f8e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flower_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=40), nullable=False),
        sa.Column("reference_cost", sa.BigInteger(), nullable=False),
        sa.Column("vase_life_days", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reference_cost >= 0", name=op.f("ck_flower_types_reference_cost_non_negative")
        ),
        sa.CheckConstraint("vase_life_days > 0", name=op.f("ck_flower_types_vase_life_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flower_types")),
        sa.UniqueConstraint("name", name=op.f("uq_flower_types_name")),
    )
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
        sa.UniqueConstraint("name", name=op.f("uq_suppliers_name")),
    )
    op.create_table(
        "bouquet_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("discount_locked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("price > 0", name=op.f("ck_bouquet_templates_price_positive")),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["staff_users.id"],
            name=op.f("fk_bouquet_templates_updated_by_id_staff_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bouquet_templates")),
        sa.UniqueConstraint("slug", name=op.f("uq_bouquet_templates_slug")),
    )
    op.create_table(
        "template_items",
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("flower_type_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_template_items_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["flower_type_id"],
            ["flower_types.id"],
            name=op.f("fk_template_items_flower_type_id_flower_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["bouquet_templates.id"],
            name=op.f("fk_template_items_template_id_bouquet_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("template_id", "flower_type_id", name=op.f("pk_template_items")),
    )
    op.create_index(
        op.f("ix_template_items_flower_type_id"), "template_items", ["flower_type_id"], unique=False
    )
    op.create_table(
        "template_price_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("old_price", sa.BigInteger(), nullable=False),
        sa.Column("new_price", sa.BigInteger(), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_id"],
            ["staff_users.id"],
            name=op.f("fk_template_price_history_changed_by_id_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["bouquet_templates.id"],
            name=op.f("fk_template_price_history_template_id_bouquet_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_price_history")),
    )
    op.create_index(
        op.f("ix_template_price_history_template_id"),
        "template_price_history",
        ["template_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_template_price_history_template_id"), table_name="template_price_history"
    )
    op.drop_table("template_price_history")
    op.drop_index(op.f("ix_template_items_flower_type_id"), table_name="template_items")
    op.drop_table("template_items")
    op.drop_table("bouquet_templates")
    op.drop_table("suppliers")
    op.drop_table("flower_types")

"""create batches and inventory movements

Revision ID: 3f3ee8b4eb61
Revises: 5b73c7feecbd
Create Date: 2026-11-23 13:12:01.182711

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3f3ee8b4eb61"
down_revision: str | None = "5b73c7feecbd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("flower_type_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("quantity_received", sa.Integer(), nullable=False),
        sa.Column("quantity_available", sa.Integer(), nullable=False),
        sa.Column("cost_per_stem", sa.BigInteger(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_expiry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshness_override", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "needs_review",
                "depleted",
                "discarded",
                name="batch_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("cost_per_stem >= 0", name=op.f("ck_batches_cost_non_negative")),
        sa.CheckConstraint(
            "expected_expiry_at > received_at", name=op.f("ck_batches_expiry_after_received")
        ),
        sa.CheckConstraint(
            "freshness_override IS NULL OR (freshness_override >= 0 AND freshness_override <= 1)",
            name=op.f("ck_batches_freshness_override_range"),
        ),
        sa.CheckConstraint(
            "quantity_available >= 0", name=op.f("ck_batches_available_non_negative")
        ),
        sa.CheckConstraint("quantity_received > 0", name=op.f("ck_batches_received_positive")),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["staff_users.id"],
            name=op.f("fk_batches_created_by_id_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["flower_type_id"],
            ["flower_types.id"],
            name=op.f("fk_batches_flower_type_id_flower_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name=op.f("fk_batches_supplier_id_suppliers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batches")),
    )
    op.create_index(
        "ix_batches_fefo",
        "batches",
        ["flower_type_id", "status", "expected_expiry_at"],
        unique=False,
    )
    op.create_index(op.f("ix_batches_supplier_id"), "batches", ["supplier_id"], unique=False)
    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "import",
                "reserve",
                "release",
                "waste",
                "adjust",
                name="movement_type",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity <> 0", name=op.f("ck_inventory_movements_quantity_non_zero")),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batches.id"],
            name=op.f("fk_inventory_movements_batch_id_batches"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["staff_users.id"],
            name=op.f("fk_inventory_movements_created_by_id_staff_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_movements")),
    )
    op.create_index(
        op.f("ix_inventory_movements_batch_id"), "inventory_movements", ["batch_id"], unique=False
    )
    op.create_index(
        op.f("ix_inventory_movements_order_id"), "inventory_movements", ["order_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_inventory_movements_order_id"), table_name="inventory_movements")
    op.drop_index(op.f("ix_inventory_movements_batch_id"), table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_index(op.f("ix_batches_supplier_id"), table_name="batches")
    op.drop_index("ix_batches_fefo", table_name="batches")
    op.drop_table("batches")

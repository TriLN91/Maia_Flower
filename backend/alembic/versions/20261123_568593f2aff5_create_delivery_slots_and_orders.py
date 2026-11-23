"""create delivery slots and orders

Revision ID: 568593f2aff5
Revises: 3f3ee8b4eb61
Create Date: 2026-11-23 13:23:10.655161

"""

from collections.abc import Sequence
from datetime import time

import sqlalchemy as sa

from alembic import op

revision: str = "568593f2aff5"
down_revision: str | None = "3f3ee8b4eb61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("default_capacity", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint(
            "default_capacity >= 0", name=op.f("ck_delivery_slots_capacity_non_negative")
        ),
        sa.CheckConstraint("end_time > start_time", name=op.f("ck_delivery_slots_end_after_start")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_slots")),
        sa.UniqueConstraint("start_time", "end_time", name=op.f("uq_delivery_slots_start_time")),
    )
    # Khung giờ mặc định (giờ VN), mỗi khung tối đa 6 đơn — chủ shop sửa được sau
    slots = sa.table(
        "delivery_slots",
        sa.column("start_time", sa.Time),
        sa.column("end_time", sa.Time),
        sa.column("default_capacity", sa.Integer),
    )
    op.bulk_insert(
        slots,
        [
            {"start_time": time(s), "end_time": time(e), "default_capacity": 6}
            for s, e in [(8, 10), (10, 12), (13, 15), (15, 17), (17, 19)]
        ],
    )
    op.create_table(
        "delivery_slot_days",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slot_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("reserved_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_closed", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint(
            "capacity >= 0", name=op.f("ck_delivery_slot_days_capacity_non_negative")
        ),
        sa.CheckConstraint(
            "reserved_count >= 0", name=op.f("ck_delivery_slot_days_reserved_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["slot_id"],
            ["delivery_slots.id"],
            name=op.f("fk_delivery_slot_days_slot_id_delivery_slots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_slot_days")),
        sa.UniqueConstraint("slot_id", "date", name=op.f("uq_delivery_slot_days_slot_id")),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("tracking_token", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending_payment",
                "paid",
                "preparing",
                "delivering",
                "completed",
                "cancelled",
                "expired",
                name="order_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("customer_phone", sa.String(length=15), nullable=False),
        sa.Column("recipient_name", sa.String(length=120), nullable=True),
        sa.Column("recipient_phone", sa.String(length=15), nullable=True),
        sa.Column("delivery_address", sa.String(length=500), nullable=False),
        sa.Column("delivery_lat", sa.Float(), nullable=True),
        sa.Column("delivery_lng", sa.Float(), nullable=True),
        sa.Column("delivery_distance_km", sa.Float(), nullable=True),
        sa.Column("delivery_slot_day_id", sa.Integer(), nullable=False),
        sa.Column("delivery_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("card_message", sa.String(length=300), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.BigInteger(), nullable=False),
        sa.Column("discount_total", sa.BigInteger(), nullable=False),
        sa.Column("delivery_fee", sa.BigInteger(), nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
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
            "subtotal >= 0 AND discount_total >= 0 AND delivery_fee >= 0",
            name=op.f("ck_orders_money"),
        ),
        sa.CheckConstraint(
            "total = subtotal - discount_total + delivery_fee", name=op.f("ck_orders_total_matches")
        ),
        sa.ForeignKeyConstraint(
            ["delivery_slot_day_id"],
            ["delivery_slot_days.id"],
            name=op.f("fk_orders_delivery_slot_day_id_delivery_slot_days"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("code", name=op.f("uq_orders_code")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_orders_idempotency_key")),
        sa.UniqueConstraint("tracking_token", name=op.f("uq_orders_tracking_token")),
    )
    op.create_index(op.f("ix_orders_customer_phone"), "orders", ["customer_phone"], unique=False)
    op.create_index(
        op.f("ix_orders_delivery_slot_day_id"), "orders", ["delivery_slot_day_id"], unique=False
    )
    op.create_index("ix_orders_status_hold", "orders", ["status", "hold_expires_at"], unique=False)
    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("template_name", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.BigInteger(), nullable=False),
        sa.Column("discount_pct", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "discount_pct >= 0 AND discount_pct <= 100", name=op.f("ck_order_items_discount_range")
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_order_items_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_items_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["bouquet_templates.id"],
            name=op.f("fk_order_items_template_id_bouquet_templates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
    )
    op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)
    op.create_table(
        "order_allocations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("flower_type_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_order_allocations_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batches.id"],
            name=op.f("fk_order_allocations_batch_id_batches"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["flower_type_id"],
            ["flower_types.id"],
            name=op.f("fk_order_allocations_flower_type_id_flower_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_items.id"],
            name=op.f("fk_order_allocations_order_item_id_order_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_allocations")),
    )
    op.create_index(
        op.f("ix_order_allocations_batch_id"), "order_allocations", ["batch_id"], unique=False
    )
    op.create_index(
        op.f("ix_order_allocations_order_item_id"),
        "order_allocations",
        ["order_item_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_inventory_movements_order_id_orders"),
        "inventory_movements",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_inventory_movements_order_id_orders"), "inventory_movements", type_="foreignkey"
    )
    op.drop_index(op.f("ix_order_allocations_order_item_id"), table_name="order_allocations")
    op.drop_index(op.f("ix_order_allocations_batch_id"), table_name="order_allocations")
    op.drop_table("order_allocations")
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_status_hold", table_name="orders")
    op.drop_index(op.f("ix_orders_delivery_slot_day_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_customer_phone"), table_name="orders")
    op.drop_table("orders")
    op.drop_table("delivery_slot_days")
    op.drop_table("delivery_slots")

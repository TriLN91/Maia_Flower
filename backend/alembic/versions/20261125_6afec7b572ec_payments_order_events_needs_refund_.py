"""payments, order events, needs_refund status

Revision ID: 6afec7b572ec
Revises: bdc5059dd475
Create Date: 2026-11-25 13:45:16.320442

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "6afec7b572ec"
down_revision: str | None = "bdc5059dd475"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enum lưu dạng VARCHAR + CHECK: autogenerate không thấy giá trị mới -> sửa CHECK bằng tay
    op.drop_constraint(op.f("ck_orders_order_status"), "orders", type_="check")
    op.create_check_constraint(
        "order_status",
        "orders",
        "status IN ('pending_payment', 'paid', 'preparing', 'delivering', 'completed', "
        "'cancelled', 'expired', 'needs_refund')",
    )
    op.create_table(
        "order_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "from_status",
            sa.Enum(
                "pending_payment",
                "paid",
                "preparing",
                "delivering",
                "completed",
                "cancelled",
                "expired",
                "needs_refund",
                name="order_event_from_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "pending_payment",
                "paid",
                "preparing",
                "delivering",
                "completed",
                "cancelled",
                "expired",
                "needs_refund",
                name="order_event_to_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["staff_users.id"],
            name=op.f("fk_order_events_actor_id_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_events_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_events")),
    )
    op.create_index(op.f("ix_order_events_order_id"), "order_events", ["order_id"], unique=False)
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("txn_ref", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "succeeded",
                "failed",
                "cancelled",
                name="payment_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("gateway_txn_no", sa.String(length=40), nullable=True),
        sa.Column("response_code", sa.String(length=10), nullable=True),
        sa.Column("needs_refund", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("raw_callback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount_positive")),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_payments_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("txn_ref", name=op.f("uq_payments_txn_ref")),
    )
    op.create_index(op.f("ix_payments_order_id"), "payments", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_orders_order_status"), "orders", type_="check")
    op.create_check_constraint(
        "order_status",
        "orders",
        "status IN ('pending_payment', 'paid', 'preparing', 'delivering', 'completed', "
        "'cancelled', 'expired')",
    )
    op.drop_index(op.f("ix_payments_order_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_order_events_order_id"), table_name="order_events")
    op.drop_table("order_events")

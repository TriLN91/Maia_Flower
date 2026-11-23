"""create staff_users

Revision ID: 59babae2f8e8
Revises:
Create Date: 2026-11-23 09:13:35.641334

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "59babae2f8e8"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "staff",
                "owner",
                name="staff_role",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_users")),
    )
    op.create_index(op.f("ix_staff_users_email"), "staff_users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_staff_users_email"), table_name="staff_users")
    op.drop_table("staff_users")

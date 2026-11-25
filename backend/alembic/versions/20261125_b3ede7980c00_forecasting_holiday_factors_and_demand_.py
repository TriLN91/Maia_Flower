"""forecasting: holiday factors and demand forecasts

Revision ID: b3ede7980c00
Revises: 3959d7c69af7
Create Date: 2026-11-25 14:58:36.214530

"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa

from alembic import op

revision: str = "b3ede7980c00"
down_revision: str | None = "3959d7c69af7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demand_forecasts",
        sa.Column("flower_type_id", sa.Integer(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("predicted_qty", sa.Float(), nullable=False),
        sa.Column("base_qty", sa.Float(), nullable=False),
        sa.Column("multiplier", sa.Float(), nullable=False),
        sa.Column("holiday", sa.String(length=120), nullable=True),
        sa.Column("history_days", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["flower_type_id"],
            ["flower_types.id"],
            name=op.f("fk_demand_forecasts_flower_type_id_flower_types"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("flower_type_id", "target_date", name=op.f("pk_demand_forecasts")),
    )
    op.create_table(
        "holiday_factors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("month_day", sa.String(length=5), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("flower_type_id", sa.Integer(), nullable=True),
        sa.Column("multiplier", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "(month_day IS NOT NULL AND start_date IS NULL AND end_date IS NULL) OR "
            "(month_day IS NULL AND start_date IS NOT NULL AND end_date IS NOT NULL "
            "AND end_date >= start_date)",
            name=op.f("ck_holiday_factors_recurring_xor_range"),
        ),
        sa.CheckConstraint("multiplier > 0", name=op.f("ck_holiday_factors_multiplier_positive")),
        sa.ForeignKeyConstraint(
            ["flower_type_id"],
            ["flower_types.id"],
            name=op.f("fk_holiday_factors_flower_type_id_flower_types"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holiday_factors")),
    )
    op.create_index(
        op.f("ix_holiday_factors_flower_type_id"),
        "holiday_factors",
        ["flower_type_id"],
        unique=False,
    )

    # Bộ hệ số lễ mặc định (áp cho mọi loại hoa) — chủ shop chỉnh / thêm riêng từng loại hoa sau.
    holidays = sa.table(
        "holiday_factors",
        sa.column("name", sa.String),
        sa.column("month_day", sa.String),
        sa.column("start_date", sa.Date),
        sa.column("end_date", sa.Date),
        sa.column("multiplier", sa.Float),
    )
    recurring = [
        ("Trước Valentine", "02-13", 1.8),
        ("Valentine", "02-14", 3.0),
        ("Trước 8/3", "03-07", 1.8),
        ("Quốc tế Phụ nữ 8/3", "03-08", 3.0),
        ("Trước 20/10", "10-19", 1.8),
        ("Phụ nữ Việt Nam 20/10", "10-20", 3.0),
        ("Trước 20/11", "11-19", 1.5),
        ("Nhà giáo Việt Nam 20/11", "11-20", 2.2),
        ("Giáng sinh", "12-24", 1.4),
    ]
    ranges = [  # ngày thay đổi theo năm (âm lịch / Chủ nhật thứ 2 của tháng 5)
        ("Ngày của Mẹ", date(2025, 5, 11), date(2025, 5, 11), 1.6),
        ("Ngày của Mẹ", date(2026, 5, 10), date(2026, 5, 10), 1.6),
        ("Ngày của Mẹ", date(2027, 5, 9), date(2027, 5, 9), 1.6),
        ("Trước Tết", date(2025, 1, 22), date(2025, 1, 28), 1.5),
        ("Tết Nguyên đán", date(2025, 1, 29), date(2025, 2, 1), 0.3),
        ("Trước Tết", date(2026, 2, 10), date(2026, 2, 16), 1.5),
        ("Tết Nguyên đán", date(2026, 2, 17), date(2026, 2, 20), 0.3),
        ("Trước Tết", date(2027, 1, 30), date(2027, 2, 5), 1.5),
        ("Tết Nguyên đán", date(2027, 2, 6), date(2027, 2, 9), 0.3),
    ]
    op.bulk_insert(
        holidays,
        [
            {"name": n, "month_day": md, "start_date": None, "end_date": None, "multiplier": m}
            for n, md, m in recurring
        ]
        + [
            {"name": n, "month_day": None, "start_date": a, "end_date": b, "multiplier": m}
            for n, a, b, m in ranges
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_holiday_factors_flower_type_id"), table_name="holiday_factors")
    op.drop_table("holiday_factors")
    op.drop_table("demand_forecasts")

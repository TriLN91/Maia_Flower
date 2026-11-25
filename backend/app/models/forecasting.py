from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HolidayFactor(Base):
    """Hệ số nhu cầu cho ngày lễ / mùa vụ.

    - Lặp lại hằng năm: đặt `month_day` ("02-14").
    - Một lần (ngày âm lịch, Ngày của Mẹ…): đặt `start_date` … `end_date`.
    - `flower_type_id` trống = áp cho mọi loại hoa; có giá trị = ghi đè riêng cho loại đó.
    """

    __tablename__ = "holiday_factors"
    __table_args__ = (
        CheckConstraint("multiplier > 0", name="multiplier_positive"),
        CheckConstraint(
            "(month_day IS NOT NULL AND start_date IS NULL AND end_date IS NULL) OR "
            "(month_day IS NULL AND start_date IS NOT NULL AND end_date IS NOT NULL "
            "AND end_date >= start_date)",
            name="recurring_xor_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    month_day: Mapped[str | None] = mapped_column(String(5))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    flower_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("flower_types.id", ondelete="CASCADE"), index=True
    )
    multiplier: Mapped[float] = mapped_column(Float)


class DemandForecast(Base):
    """Dự báo số cành bán được của một loại hoa trong một ngày (giờ VN)."""

    __tablename__ = "demand_forecasts"

    flower_type_id: Mapped[int] = mapped_column(
        ForeignKey("flower_types.id", ondelete="CASCADE"), primary_key=True
    )
    target_date: Mapped[date] = mapped_column(Date, primary_key=True)
    predicted_qty: Mapped[float] = mapped_column(Float)
    base_qty: Mapped[float] = mapped_column(Float)  # trước hệ số lễ
    multiplier: Mapped[float] = mapped_column(Float)
    holiday: Mapped[str | None] = mapped_column(String(120))
    history_days: Mapped[int] = mapped_column(Integer)  # số ngày lịch sử dùng để tính
    model_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

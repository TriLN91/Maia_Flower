from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UrgencyScore(Base):
    """Ảnh chụp mới nhất của bộ máy "Cần bán gấp" cho một loại hoa (ghi đè mỗi lần chạy)."""

    __tablename__ = "urgency_scores"

    flower_type_id: Mapped[int] = mapped_column(
        ForeignKey("flower_types.id", ondelete="CASCADE"), primary_key=True
    )
    expiring_qty: Mapped[int] = mapped_column(Integer)  # cành bán được, hết hạn trong N ngày
    expected_demand: Mapped[float] = mapped_column(Float)  # dự kiến bán trong N ngày
    surplus: Mapped[int] = mapped_column(Integer)  # dư thừa = sắp hết hạn − dự kiến bán
    min_days_left: Mapped[float | None] = mapped_column(Float)
    avg_freshness: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)  # dư thừa × (1 − độ tươi TB) — để xếp hạng
    discount_pct: Mapped[int] = mapped_column(Integer)  # mức giảm đề xuất cho loại hoa
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TemplateDiscount(Base):
    """Mức giảm giá ĐANG áp dụng cho một mẫu. Không có dòng = không giảm."""

    __tablename__ = "template_discounts"
    __table_args__ = (CheckConstraint("current_pct BETWEEN 0 AND 90", name="pct_range"),)

    template_id: Mapped[int] = mapped_column(
        ForeignKey("bouquet_templates.id", ondelete="CASCADE"), primary_key=True
    )
    current_pct: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TemplateDiscountLog(Base):
    """Mỗi lần mức giảm của một mẫu thay đổi: cũ, mới, và VÌ SAO (hoa nào dư, dự báo bao nhiêu,
    bị trần/sàn/bước giới hạn chặn ra sao)."""

    __tablename__ = "template_discount_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("bouquet_templates.id", ondelete="CASCADE"), index=True
    )
    old_pct: Mapped[int] = mapped_column(Integer)
    new_pct: Mapped[int] = mapped_column(Integer)
    reason: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

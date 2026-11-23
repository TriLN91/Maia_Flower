from datetime import date, time

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DeliverySlot(Base):
    """Khung giờ giao mẫu, lặp lại mỗi ngày (vd. 8:00–10:00, tối đa 6 đơn).

    Giờ ở đây là giờ địa phương của shop (Asia/Ho_Chi_Minh).
    """

    __tablename__ = "delivery_slots"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="end_after_start"),
        CheckConstraint("default_capacity >= 0", name="capacity_non_negative"),
        UniqueConstraint("start_time", "end_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    default_capacity: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class DeliverySlotDay(Base):
    """Sức chứa thực tế của một khung giờ trong một ngày cụ thể.

    Tạo lười (lazy) khi có người đặt lần đầu; chủ shop có thể ghi đè sức chứa / đóng khung.
    `reserved_count` tăng khi giữ chỗ, giảm khi nhả — được khóa dòng khi checkout.
    """

    __tablename__ = "delivery_slot_days"
    __table_args__ = (
        UniqueConstraint("slot_id", "date"),
        CheckConstraint("capacity >= 0", name="capacity_non_negative"),
        CheckConstraint("reserved_count >= 0", name="reserved_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("delivery_slots.id", ondelete="RESTRICT"))
    date: Mapped[date] = mapped_column(Date)
    capacity: Mapped[int] = mapped_column(Integer)
    reserved_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    slot: Mapped[DeliverySlot] = relationship(lazy="joined")

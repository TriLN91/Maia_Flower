import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.catalog import BouquetTemplate
from app.models.delivery import DeliverySlotDay
from app.models.inventory import Batch, _str_enum


class OrderStatus(enum.StrEnum):
    PENDING_PAYMENT = "pending_payment"  # đã giữ hoa + khung giờ, chờ thanh toán
    PAID = "paid"
    PREPARING = "preparing"  # thợ đang bó
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"  # quá hạn giữ chỗ mà chưa thanh toán


class Order(TimestampMixin, Base):
    """Đơn của khách vãng lai (không có tài khoản)."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total = subtotal - discount_total + delivery_fee", name="total_matches"),
        CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND delivery_fee >= 0", name="money"
        ),
        # Job nhả giữ chỗ quét theo (status, hold_expires_at)
        Index("ix_orders_status_hold", "status", "hold_expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # MF-251123-7K2Q
    tracking_token: Mapped[str] = mapped_column(String(64), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    # Hash nội dung request: cùng key nhưng khác nội dung -> từ chối
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[OrderStatus] = mapped_column(
        _str_enum(OrderStatus, "order_status"), default=OrderStatus.PENDING_PAYMENT
    )

    customer_name: Mapped[str] = mapped_column(String(120))
    customer_phone: Mapped[str] = mapped_column(String(15), index=True)
    recipient_name: Mapped[str | None] = mapped_column(String(120))
    recipient_phone: Mapped[str | None] = mapped_column(String(15))
    delivery_address: Mapped[str] = mapped_column(String(500))
    delivery_lat: Mapped[float | None] = mapped_column(Float)
    delivery_lng: Mapped[float | None] = mapped_column(Float)
    delivery_distance_km: Mapped[float | None] = mapped_column(Float)
    delivery_slot_day_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_slot_days.id", ondelete="RESTRICT"), index=True
    )
    delivery_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivery_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    card_message: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text)

    subtotal: Mapped[int] = mapped_column(BigInteger)
    discount_total: Mapped[int] = mapped_column(BigInteger, default=0)
    delivery_fee: Mapped[int] = mapped_column(BigInteger)
    total: Mapped[int] = mapped_column(BigInteger)
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    slot_day: Mapped[DeliverySlotDay] = relationship(lazy="joined")

    @property
    def customer_phone_masked(self) -> str:
        """0909123456 -> 0909***456 (hiển thị cho khách, tránh lộ đủ số qua link theo dõi)."""
        p = self.customer_phone
        return p[:4] + "***" + p[-3:] if len(p) >= 7 else "***"


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("discount_pct >= 0 AND discount_pct <= 100", name="discount_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("bouquet_templates.id", ondelete="RESTRICT")
    )
    # Snapshot lúc đặt: đổi giá/tên mẫu sau này không ảnh hưởng đơn cũ
    template_name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(BigInteger)
    discount_pct: Mapped[int] = mapped_column(Integer, default=0)
    line_total: Mapped[int] = mapped_column(BigInteger)

    order: Mapped[Order] = relationship(back_populates="items")
    template: Mapped[BouquetTemplate] = relationship()
    allocations: Mapped[list["OrderAllocation"]] = relationship(
        back_populates="order_item", cascade="all, delete-orphan", order_by="OrderAllocation.id"
    )


class OrderAllocation(Base):
    """Kết quả FEFO: dòng đơn này lấy bao nhiêu cành từ lô nào (để thợ biết lấy hoa ở đâu,
    và để nhả đúng lô khi hủy)."""

    __tablename__ = "order_allocations"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), index=True
    )
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="RESTRICT"), index=True)
    flower_type_id: Mapped[int] = mapped_column(ForeignKey("flower_types.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer)

    order_item: Mapped[OrderItem] = relationship(back_populates="allocations")
    batch: Mapped[Batch] = relationship(lazy="joined")

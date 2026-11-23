import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.catalog import FlowerType, Supplier


def _str_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class BatchStatus(enum.StrEnum):
    ACTIVE = "active"  # đang bán được
    NEEDS_REVIEW = "needs_review"  # quá hạn, chờ chủ shop xác nhận bỏ hay gia hạn (job đêm)
    DEPLETED = "depleted"  # đã hết hàng (bán/giữ chỗ/hỏng hết)
    DISCARDED = "discarded"  # đã bỏ phần còn lại


class MovementType(enum.StrEnum):
    """Mỗi loại thay đổi `batches.quantity_available` (âm = trừ, dương = cộng).

    Bán xong (thanh toán thành công) không làm đổi số còn bán được — hoa đã bị trừ lúc giữ chỗ —
    nên không có loại SELL; trạng thái bán nằm ở phân bổ của đơn hàng (ngày 4).
    """

    IMPORT = "import"  # nhập lô (+)
    RESERVE = "reserve"  # giữ cho đơn chờ thanh toán (−)
    RELEASE = "release"  # nhả giữ chỗ (+)
    WASTE = "waste"  # hoa hỏng/héo (−)
    ADJUST = "adjust"  # điều chỉnh theo kiểm kê (±)


class Batch(TimestampMixin, Base):
    """Một lần nhập hàng của một loại hoa. Mỗi lô có hạn dùng riêng."""

    __tablename__ = "batches"
    __table_args__ = (
        CheckConstraint("quantity_received > 0", name="received_positive"),
        CheckConstraint("quantity_available >= 0", name="available_non_negative"),
        CheckConstraint("cost_per_stem >= 0", name="cost_non_negative"),
        CheckConstraint("expected_expiry_at > received_at", name="expiry_after_received"),
        CheckConstraint(
            "freshness_override IS NULL OR (freshness_override >= 0 AND freshness_override <= 1)",
            name="freshness_override_range",
        ),
        # Phục vụ truy vấn FEFO: lô còn bán được của một loại hoa, hết hạn sớm nhất trước
        Index("ix_batches_fefo", "flower_type_id", "status", "expected_expiry_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    flower_type_id: Mapped[int] = mapped_column(ForeignKey("flower_types.id", ondelete="RESTRICT"))
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True
    )
    quantity_received: Mapped[int] = mapped_column(Integer)
    quantity_available: Mapped[int] = mapped_column(Integer)
    cost_per_stem: Mapped[int] = mapped_column(BigInteger)  # VNĐ
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expected_expiry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Thợ chỉnh tay khi thấy hoa xuống nhanh hơn dự kiến (0..1). Null = tính theo thời gian.
    freshness_override: Mapped[float | None] = mapped_column(Float)
    status: Mapped[BatchStatus] = mapped_column(
        _str_enum(BatchStatus, "batch_status"), default=BatchStatus.ACTIVE
    )
    note: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )

    flower_type: Mapped[FlowerType] = relationship(lazy="joined")
    supplier: Mapped[Supplier] = relationship(lazy="joined")


class InventoryMovement(Base):
    """Sổ kho bất biến: chỉ thêm, không sửa/xóa.

    Bất biến: batches.quantity_available == SUM(inventory_movements.quantity) của lô đó.
    """

    __tablename__ = "inventory_movements"
    __table_args__ = (CheckConstraint("quantity <> 0", name="quantity_non_zero"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="RESTRICT"), index=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[MovementType] = mapped_column(_str_enum(MovementType, "movement_type"))
    quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

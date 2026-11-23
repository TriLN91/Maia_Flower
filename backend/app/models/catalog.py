from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class FlowerType(TimestampMixin, Base):
    """Một loại hoa bán theo cành (vd. Hồng đỏ Đà Lạt)."""

    __tablename__ = "flower_types"
    __table_args__ = (
        CheckConstraint("vase_life_days > 0", name="vase_life_positive"),
        CheckConstraint("reference_cost >= 0", name="reference_cost_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    color: Mapped[str] = mapped_column(String(40))
    # Giá vốn tham khảo / cành (VNĐ). Giá vốn thực tế lấy từ các lô nhập (ngày 3).
    reference_cost: Mapped[int] = mapped_column(BigInteger, default=0)
    # Số ngày hoa giữ được độ tươi kể từ khi nhập
    vase_life_days: Mapped[int] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class BouquetTemplate(TimestampMixin, Base):
    """Mẫu bó hoa khách chọn. Giá do chủ shop nhập tay; công thức là danh sách cành cố định."""

    __tablename__ = "bouquet_templates"
    __table_args__ = (CheckConstraint("price > 0", name="price_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[int] = mapped_column(BigInteger)  # VNĐ
    # true = không bao giờ áp giảm giá động cho mẫu này (vd. mẫu cao cấp)
    discount_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )

    items: Mapped[list["TemplateItem"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateItem.flower_type_id",
    )


class TemplateItem(Base):
    """Một dòng trong công thức: mẫu X cần N cành loại hoa Y."""

    __tablename__ = "template_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    template_id: Mapped[int] = mapped_column(
        ForeignKey("bouquet_templates.id", ondelete="CASCADE"), primary_key=True
    )
    flower_type_id: Mapped[int] = mapped_column(
        ForeignKey("flower_types.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)

    template: Mapped[BouquetTemplate] = relationship(back_populates="items")
    flower_type: Mapped[FlowerType] = relationship(lazy="joined")


class TemplatePriceHistory(Base):
    __tablename__ = "template_price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("bouquet_templates.id", ondelete="CASCADE"), index=True
    )
    old_price: Mapped[int] = mapped_column(BigInteger)
    new_price: Mapped[int] = mapped_column(BigInteger)
    changed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

import enum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class StaffRole(enum.StrEnum):
    STAFF = "staff"
    OWNER = "owner"


class StaffUser(TimestampMixin, Base):
    """Tài khoản nội bộ (thợ bó, chủ shop). Khách mua hàng không có tài khoản."""

    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[StaffRole] = mapped_column(
        Enum(
            StaffRole,
            name="staff_role",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=StaffRole.STAFF,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

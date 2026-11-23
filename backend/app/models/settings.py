from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShopSetting(Base):
    """Cài đặt của shop theo nhóm (vd. 'delivery'), lưu JSON và được kiểm tra bằng Pydantic.

    Một nhóm = một dòng: đổi cả nhóm cùng lúc nên không bao giờ ở trạng thái nửa cũ nửa mới.
    """

    __tablename__ = "shop_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

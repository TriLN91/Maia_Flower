from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StaffUser
from app.models.settings import ShopSetting
from app.schemas.settings import DeliverySettings

DELIVERY_KEY = "delivery"


async def get_delivery_settings(session: AsyncSession) -> DeliverySettings:
    """Chưa có dòng nào -> dùng giá trị mặc định (bảng phí mẫu trong DESIGN.md)."""
    row = await session.get(ShopSetting, DELIVERY_KEY)
    return DeliverySettings.model_validate(row.value) if row else DeliverySettings()


async def save_delivery_settings(
    session: AsyncSession, actor: StaffUser, data: DeliverySettings
) -> DeliverySettings:
    value = data.model_dump(mode="json")
    await session.execute(
        insert(ShopSetting)
        .values(key=DELIVERY_KEY, value=value, updated_by_id=actor.id)
        .on_conflict_do_update(
            index_elements=[ShopSetting.key],
            set_={"value": value, "updated_by_id": actor.id},
        )
    )
    await session.commit()
    return data

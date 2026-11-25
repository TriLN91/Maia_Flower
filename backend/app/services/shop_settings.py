from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StaffUser
from app.models.settings import ShopSetting
from app.schemas.settings import DeliverySettings, PricingSettings

DELIVERY_KEY = "delivery"
PRICING_KEY = "pricing"


async def _get[M: BaseModel](session: AsyncSession, key: str, model: type[M]) -> M:
    """Chưa có dòng nào -> dùng giá trị mặc định của model (các con số mẫu trong DESIGN.md)."""
    row = await session.get(ShopSetting, key)
    return model.model_validate(row.value) if row else model()


async def _save[M: BaseModel](session: AsyncSession, key: str, actor: StaffUser, data: M) -> M:
    value = data.model_dump(mode="json")
    await session.execute(
        insert(ShopSetting)
        .values(key=key, value=value, updated_by_id=actor.id)
        .on_conflict_do_update(
            index_elements=[ShopSetting.key],
            set_={"value": value, "updated_by_id": actor.id},
        )
    )
    await session.commit()
    return data


async def get_delivery_settings(session: AsyncSession) -> DeliverySettings:
    return await _get(session, DELIVERY_KEY, DeliverySettings)


async def save_delivery_settings(
    session: AsyncSession, actor: StaffUser, data: DeliverySettings
) -> DeliverySettings:
    return await _save(session, DELIVERY_KEY, actor, data)


async def get_pricing_settings(session: AsyncSession) -> PricingSettings:
    return await _get(session, PRICING_KEY, PricingSettings)


async def save_pricing_settings(
    session: AsyncSession, actor: StaffUser, data: PricingSettings
) -> PricingSettings:
    return await _save(session, PRICING_KEY, actor, data)

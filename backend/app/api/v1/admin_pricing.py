from collections.abc import Sequence
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import CurrentOwner, CurrentStaff, SessionDep
from app.models import FlowerType, TemplateDiscountLog, UrgencyScore
from app.schemas.settings import PricingSettings
from app.services import pricing
from app.services.catalog import get_template
from app.services.inventory import utcnow
from app.services.shop_settings import get_pricing_settings, save_pricing_settings

router = APIRouter(prefix="/admin", tags=["admin: pricing"])


class UrgencyOut(BaseModel):
    flower_type_id: int
    name: str
    expiring_qty: int
    expected_demand: float
    surplus: int
    min_days_left: float | None
    avg_freshness: float | None
    score: float
    discount_pct: int
    computed_at: datetime


class DiscountLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_pct: int
    new_pct: int
    reason: dict
    created_at: datetime


class RecomputeOut(BaseModel):
    computed_at: datetime
    flowers_in_surplus: int
    templates_discounted: int
    templates_changed: int


@router.get("/urgency", response_model=list[UrgencyOut])
async def urgency(session: SessionDep, _: CurrentStaff) -> list[UrgencyOut]:
    """Bảng "Cần bán gấp": loại hoa sắp hết hạn mà dự kiến bán không hết, xếp theo mức gấp."""
    rows = (
        await session.execute(
            select(UrgencyScore, FlowerType.name)
            .join(FlowerType, FlowerType.id == UrgencyScore.flower_type_id)
            .order_by(UrgencyScore.score.desc(), FlowerType.name)
        )
    ).all()
    fields = [c for c in UrgencyOut.model_fields if c != "name"]
    return [UrgencyOut(**{c: getattr(u, c) for c in fields}, name=name) for u, name in rows]


@router.get("/templates/{template_id}/discount-log", response_model=list[DiscountLogOut])
async def discount_log(
    session: SessionDep, _: CurrentStaff, template_id: int
) -> Sequence[TemplateDiscountLog]:
    """Vì sao mẫu này đang được giảm giá (hoa nào dư, bao nhiêu, bị rào chắn nào giới hạn)."""
    await get_template(session, template_id)
    return (
        await session.scalars(
            select(TemplateDiscountLog)
            .where(TemplateDiscountLog.template_id == template_id)
            .order_by(TemplateDiscountLog.id.desc())
            .limit(50)
        )
    ).all()


@router.post("/pricing/recompute", response_model=RecomputeOut)
async def recompute(session: SessionDep, _: CurrentOwner) -> RecomputeOut:
    """Chạy tay bộ máy (bình thường job Celery chạy mỗi giờ)."""
    return RecomputeOut(**(await pricing.recompute(session, utcnow())).__dict__)


@router.get("/settings/pricing", response_model=PricingSettings, tags=["admin: settings"])
async def get_pricing(session: SessionDep, _: CurrentOwner) -> PricingSettings:
    return await get_pricing_settings(session)


@router.put("/settings/pricing", response_model=PricingSettings, tags=["admin: settings"])
async def put_pricing(
    session: SessionDep, owner: CurrentOwner, body: PricingSettings
) -> PricingSettings:
    """Lưu và tính lại ngay — tắt công tắc tổng thì mọi mẫu về giá gốc lập tức."""
    saved = await save_pricing_settings(session, owner, body)
    await pricing.recompute(session, utcnow())
    return saved

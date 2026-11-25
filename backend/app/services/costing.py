"""Giá vốn mẫu bó hoa và cảnh báo biên lợi nhuận."""

import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Batch, BatchStatus
from app.schemas.catalog import FlowerBrief
from app.schemas.inventory import CostLine, TemplateCostOut
from app.services.catalog import get_template
from app.services.shop_settings import get_pricing_settings

BELOW_COST = "BELOW_COST"
LOW_MARGIN_AT_MAX_DISCOUNT = "LOW_MARGIN_AT_MAX_DISCOUNT"


async def unit_costs(session: AsyncSession, flower_type_ids: set[int]) -> dict[int, int]:
    """Giá vốn TB có trọng số theo số cành của các lô còn hàng, làm tròn lên (thận trọng)."""
    if not flower_type_ids:
        return {}
    rows = (
        await session.execute(
            select(
                Batch.flower_type_id,
                func.sum(Batch.quantity_available * Batch.cost_per_stem),
                func.sum(Batch.quantity_available),
            )
            .where(
                Batch.flower_type_id.in_(flower_type_ids),
                Batch.status.in_([BatchStatus.ACTIVE, BatchStatus.NEEDS_REVIEW]),
                Batch.quantity_available > 0,
            )
            .group_by(Batch.flower_type_id)
        )
    ).all()
    return {fid: math.ceil(total_cost / qty) for fid, total_cost, qty in rows}


async def template_cost(session: AsyncSession, template_id: int) -> TemplateCostOut:
    settings = await get_pricing_settings(session)
    template = await get_template(session, template_id)
    costs = await unit_costs(session, {i.flower_type_id for i in template.items})

    lines: list[CostLine] = []
    for item in template.items:
        if item.flower_type_id in costs:
            unit, source = costs[item.flower_type_id], "batches"
        else:  # chưa có lô nào còn hàng -> dùng giá tham khảo
            unit, source = item.flower_type.reference_cost, "reference"
        lines.append(
            CostLine(
                flower_type=FlowerBrief.model_validate(item.flower_type),
                quantity=item.quantity,
                unit_cost=unit,
                line_cost=unit * item.quantity,
                cost_source=source,
            )
        )

    cost = sum(line.line_cost for line in lines)
    price = template.price
    lowest = math.floor(price * (100 - settings.max_discount_pct) / 100)
    floor_price = math.ceil(cost * (100 + settings.min_margin_pct) / 100)

    warnings: list[str] = []
    if price < cost:
        warnings.append(BELOW_COST)
    if lowest < floor_price:
        warnings.append(LOW_MARGIN_AT_MAX_DISCOUNT)

    return TemplateCostOut(
        template_id=template.id,
        price=price,
        cost=cost,
        margin_pct=round((price - cost) / cost * 100, 2) if cost else None,
        max_discount_pct=settings.max_discount_pct,
        lowest_price_after_discount=lowest,
        min_margin_pct=settings.min_margin_pct,
        price_floor=floor_price,
        warnings=warnings,
        lines=lines,
    )

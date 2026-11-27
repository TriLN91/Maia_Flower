"""Bộ máy "Cần bán gấp" + giảm giá động tự động.

1) Mỗi loại hoa:  sắp_hết_hạn (cành bán được, hết hạn trong N ngày) so với nhu_cầu_dự_kiến
   trong N ngày -> dư_thừa. Có dư thừa thì loại hoa được đề xuất giảm theo bậc số ngày còn lại.
2) Mỗi mẫu: mức giảm = TB có trọng số (theo số cành trong công thức) của mức giảm các loại hoa,
   rồi qua các rào chắn: khóa mẫu, công tắc tổng, trần giảm, sàn biên lợi nhuận, bước tối đa.
3) Ghi mức đang áp dụng + nhật ký lý do. Checkout đọc mức này và chụp (snapshot) vào đơn.

Chỉ giảm khi dự kiến THỰC SỰ thừa — không giảm chỉ vì hoa sắp hết hạn nếu đằng nào cũng bán hết.
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Batch,
    BouquetTemplate,
    FlowerType,
    Order,
    OrderAllocation,
    OrderItem,
    OrderStatus,
    TemplateDiscount,
    TemplateDiscountLog,
    UrgencyScore,
)
from app.schemas.settings import PricingSettings
from app.services.costing import unit_costs
from app.services.forecasting import expected_demand as forecast_demand
from app.services.inventory import batch_freshness
from app.services.reservations import sellable_filter
from app.services.shop_settings import get_pricing_settings

# Đơn đã nhả hàng / không giao không được tính là "đã bán"
NOT_SOLD = (OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.NEEDS_REFUND)


# =====================================================================
# Quyết định mức giảm cho một mẫu (hàm thuần)
# =====================================================================
@dataclass
class Decision:
    new_pct: int
    raw_pct: float  # TB có trọng số trước rào chắn
    target_pct: int  # sau trần + sàn, trước giới hạn bước
    limits: list[str] = field(default_factory=list)  # rào chắn nào đã chặn
    margin_cap_pct: int | None = None


def max_pct_for_margin(price: int, cost: int, min_margin_pct: int) -> int:
    """Mức giảm lớn nhất mà giá sau giảm vẫn ≥ vốn × (1 + biên tối thiểu).

    price × (100 − p) / 100 ≥ cost × (100 + m) / 100  ⇔  p ≤ (100·price − cost·(100 + m)) / price
    (tính bằng số nguyên để không lệch vì số thực)."""
    if price <= 0:
        return 0
    return max(0, min(100, (100 * price - cost * (100 + min_margin_pct)) // price))


def decide_discount(
    *,
    recipe: Mapping[int, int],
    flower_pct: Mapping[int, int],
    price: int,
    cost: int,
    current_pct: int,
    settings: PricingSettings,
    locked: bool = False,
) -> Decision:
    total_stems = sum(recipe.values())
    raw = (
        sum(qty * flower_pct.get(fid, 0) for fid, qty in recipe.items()) / total_stems
        if total_stems
        else 0.0
    )
    if not settings.enabled or locked:
        # Tắt / khóa: về giá gốc NGAY, không đi qua giới hạn bước
        return Decision(0, raw, 0, ["disabled" if not settings.enabled else "locked"])

    target = math.floor(raw + 0.5)  # làm tròn nửa lên
    limits: list[str] = []
    if target > settings.max_discount_pct:
        target, _ = settings.max_discount_pct, limits.append("max_discount")
    cap = max_pct_for_margin(price, cost, settings.min_margin_pct)
    if target > cap:
        target, _ = cap, limits.append("margin_floor")

    new = target
    if new > current_pct + settings.max_step_pct:
        new, _ = current_pct + settings.max_step_pct, limits.append("step")
    elif new < current_pct - settings.max_step_pct:
        new, _ = current_pct - settings.max_step_pct, limits.append("step")
    return Decision(new, round(raw, 2), target, limits, cap)


# =====================================================================
# Điểm gấp của từng loại hoa
# =====================================================================
@dataclass
class FlowerUrgency:
    flower_type_id: int
    name: str
    expiring_qty: int
    expected_demand: float
    surplus: int
    min_days_left: float | None
    avg_freshness: float | None
    score: float
    discount_pct: int


async def estimate_demand(
    session: AsyncSession, now: datetime, settings: PricingSettings
) -> dict[int, float]:
    """Dự phòng khi chưa có dự báo: TB số cành bán/ngày trong `demand_lookback_days` qua
    × `horizon_days`."""
    since = now - timedelta(days=settings.demand_lookback_days)
    rows = (
        await session.execute(
            select(OrderAllocation.flower_type_id, func.sum(OrderAllocation.quantity))
            .join(OrderItem, OrderItem.id == OrderAllocation.order_item_id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.created_at >= since, Order.status.not_in(NOT_SOLD))
            .group_by(OrderAllocation.flower_type_id)
        )
    ).all()
    per_day = {fid: total / settings.demand_lookback_days for fid, total in rows}
    return {fid: v * settings.horizon_days for fid, v in per_day.items()}


async def compute_urgency(
    session: AsyncSession, now: datetime, settings: PricingSettings
) -> list[FlowerUrgency]:
    soon = now + timedelta(days=settings.horizon_days)
    flowers = (
        await session.scalars(select(FlowerType).where(FlowerType.is_active.is_(True)))
    ).all()
    batches = (await session.scalars(select(Batch).where(*sellable_filter(now)))).all()
    by_flower: dict[int, list[Batch]] = defaultdict(list)
    for b in batches:
        if b.expected_expiry_at <= soon:
            by_flower[b.flower_type_id].append(b)
    # Ưu tiên dự báo (thứ trong tuần × hệ số lễ); chưa có thì dùng TB lịch sử gần đây
    demand = await forecast_demand(session, now, settings.horizon_days)
    if demand is None:
        demand = await estimate_demand(session, now, settings)

    out = []
    for f in flowers:
        expiring = by_flower.get(f.id, [])
        qty = sum(b.quantity_available for b in expiring)
        infos = [(b, batch_freshness(b, now)) for b in expiring]
        min_days = min((i.days_left for _, i in infos), default=None)
        avg_fresh = sum(i.freshness * b.quantity_available for b, i in infos) / qty if qty else None
        expected = demand.get(f.id, 0.0)
        surplus = max(0, qty - math.ceil(expected))
        pct = (
            settings.flower_discount(min_days)
            if surplus >= settings.min_surplus_stems and min_days is not None
            else 0
        )
        score = round(surplus * (1 - (avg_fresh or 0)), 2)
        out.append(
            FlowerUrgency(
                f.id,
                f.name,
                qty,
                round(expected, 2),
                surplus,
                None if min_days is None else round(min_days, 2),
                None if avg_fresh is None else round(avg_fresh, 4),
                score,
                pct,
            )
        )
    return sorted(out, key=lambda u: (-u.score, u.name))


# =====================================================================
# Tính lại toàn bộ
# =====================================================================
@dataclass
class RecomputeResult:
    computed_at: datetime
    flowers_in_surplus: int
    templates_discounted: int
    templates_changed: int


async def current_discounts(session: AsyncSession, template_ids: Iterable[int]) -> dict[int, int]:
    ids = list(template_ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(TemplateDiscount.template_id, TemplateDiscount.current_pct).where(
            TemplateDiscount.template_id.in_(ids)
        )
    )
    return {tid: pct for tid, pct in rows.all()}


async def recompute(session: AsyncSession, now: datetime) -> RecomputeResult:
    # Khóa tư vấn (advisory lock) theo transaction: hai lần chạy cùng lúc (job + bấm tay)
    # sẽ chạy lần lượt, không ghi đè nhau với giới hạn bước sai.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('maia:pricing'))"))
    settings = await get_pricing_settings(session)
    urgency = await compute_urgency(session, now, settings)
    flower_pct = {u.flower_type_id: u.discount_pct for u in urgency}
    by_id = {u.flower_type_id: u for u in urgency}

    await session.execute(delete(UrgencyScore))
    if urgency:
        await session.execute(
            insert(UrgencyScore),
            [
                {k: v for k, v in asdict(u).items() if k != "name"} | {"computed_at": now}
                for u in urgency
            ],
        )

    templates = (
        await session.scalars(select(BouquetTemplate).options(selectinload(BouquetTemplate.items)))
    ).all()
    costs = await unit_costs(session, {i.flower_type_id for t in templates for i in t.items})
    ref_costs = dict(
        (await session.execute(select(FlowerType.id, FlowerType.reference_cost))).all()
    )
    current = await current_discounts(session, [t.id for t in templates])

    changed = discounted = 0
    for t in templates:
        recipe = {i.flower_type_id: i.quantity for i in t.items}
        cost = sum(costs.get(fid, ref_costs.get(fid, 0)) * q for fid, q in recipe.items())
        old = current.get(t.id, 0)
        d = decide_discount(
            recipe=recipe,
            flower_pct=flower_pct,
            price=t.price,
            cost=cost,
            current_pct=old,
            settings=settings,
            locked=t.discount_locked or not t.is_active,
        )
        if d.new_pct:
            discounted += 1
        if d.new_pct == old:
            continue
        changed += 1
        await session.execute(
            insert(TemplateDiscount)
            .values(template_id=t.id, current_pct=d.new_pct, updated_at=now)
            .on_conflict_do_update(
                index_elements=[TemplateDiscount.template_id],
                set_={"current_pct": d.new_pct, "updated_at": now},
            )
        )
        session.add(
            TemplateDiscountLog(
                template_id=t.id,
                old_pct=old,
                new_pct=d.new_pct,
                created_at=now,
                reason={
                    "raw_pct": d.raw_pct,
                    "target_pct": d.target_pct,
                    "limits": d.limits,
                    "margin_cap_pct": d.margin_cap_pct,
                    "cost": cost,
                    "price": t.price,
                    "flowers": [
                        {
                            "flower_type_id": fid,
                            "name": by_id[fid].name,
                            "stems_in_recipe": q,
                            "expiring_qty": by_id[fid].expiring_qty,
                            "expected_demand": by_id[fid].expected_demand,
                            "surplus": by_id[fid].surplus,
                            "discount_pct": by_id[fid].discount_pct,
                        }
                        for fid, q in recipe.items()
                        if fid in by_id and by_id[fid].discount_pct
                    ],
                },
            )
        )
    await session.commit()
    return RecomputeResult(now, sum(1 for u in urgency if u.surplus), discounted, changed)


async def fresh_today(session: AsyncSession, limit: int = 6) -> list[tuple[BouquetTemplate, int]]:
    """Mục "Tươi nhất hôm nay": mẫu đang giảm giá / dùng nhiều cành đang dư thừa nhất."""
    surplus = dict(
        (
            await session.execute(
                # Chỉ hoa đang thực sự được giảm (dư dưới ngưỡng tối thiểu thì không tính)
                select(UrgencyScore.flower_type_id, UrgencyScore.surplus).where(
                    UrgencyScore.discount_pct > 0
                )
            )
        ).all()
    )
    templates = (
        await session.scalars(
            select(BouquetTemplate)
            .options(selectinload(BouquetTemplate.items))
            .where(BouquetTemplate.is_active.is_(True))
        )
    ).all()
    discounts = await current_discounts(session, [t.id for t in templates])
    ranked = []
    for t in templates:
        urgent_stems = sum(i.quantity for i in t.items if i.flower_type_id in surplus)
        pct = discounts.get(t.id, 0)
        if urgent_stems or pct:
            ranked.append((pct, urgent_stems, t))
    ranked.sort(key=lambda r: (-r[0], -r[1], r[2].name))
    return [(t, pct) for pct, _, t in ranked[:limit]]

"""Dự báo nhu cầu (phần đụng DB): đọc lịch sử bán, lưu dự báo 14 ngày, gợi ý nhập hàng,
backtest, và cung cấp "nhu cầu dự kiến" cho bộ máy giảm giá."""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Date, cast, delete, func, select
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Batch,
    DemandForecast,
    FlowerType,
    HolidayFactor,
    Order,
    OrderAllocation,
    OrderItem,
    OrderStatus,
)
from app.services.delivery_slots import shop_tz
from app.services.forecast_model import (
    DEFAULT_WEEKS,
    MODEL_VERSION,
    BacktestResult,
    HolidayRule,
    backtest,
    factor_fn,
    forecast_day,
    restock_quantity,
)
from app.services.reservations import sellable_filter

NOT_SOLD = (OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.NEEDS_REFUND)


def local_today(now: datetime) -> date:
    return now.astimezone(shop_tz()).date()


async def load_rules(session: AsyncSession) -> list[HolidayRule]:
    rows = (await session.scalars(select(HolidayFactor))).all()
    return [
        HolidayRule(r.name, r.multiplier, r.month_day, r.start_date, r.end_date, r.flower_type_id)
        for r in rows
    ]


async def load_daily_sales(
    session: AsyncSession, start: date, end: date
) -> dict[int, dict[date, float]]:
    """Số cành bán mỗi ngày (theo NGÀY ĐẶT, giờ VN) cho mọi loại hoa đang bán, điền 0 cho ngày
    không bán. Lưu ý: đây là nhu cầu "đã đáp ứng" — đơn mất vì hết hoa không được ghi nhận."""
    local_day = cast(func.timezone(shop_tz().key, Order.created_at), Date)
    rows = (
        await session.execute(
            select(OrderAllocation.flower_type_id, local_day, func.sum(OrderAllocation.quantity))
            .join(OrderItem, OrderItem.id == OrderAllocation.order_item_id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.status.not_in(NOT_SOLD), local_day >= start, local_day <= end)
            .group_by(OrderAllocation.flower_type_id, local_day)
        )
    ).all()
    flower_ids = (
        await session.scalars(select(FlowerType.id).where(FlowerType.is_active.is_(True)))
    ).all()
    days = [start + timedelta(days=k) for k in range((end - start).days + 1)]
    out = {fid: dict.fromkeys(days, 0.0) for fid in flower_ids}
    for fid, d, qty in rows:
        if fid in out:
            out[fid][d] = float(qty)
    return out


def _history_start(today: date, weeks: int) -> date:
    return today - timedelta(days=7 * weeks + 7)


# ============================================================ Lưu dự báo
async def recompute_forecasts(session: AsyncSession, now: datetime, days: int = 14) -> int:
    today = local_today(now)
    rules = await load_rules(session)
    history = await load_daily_sales(
        session, _history_start(today, DEFAULT_WEEKS), today - timedelta(days=1)
    )
    rows = []
    for fid, hist in history.items():
        fn = factor_fn(rules, fid)
        for k in range(days):
            target = today + timedelta(days=k)
            f = forecast_day(hist, today, target, fn)
            rows.append(
                {
                    "flower_type_id": fid,
                    "target_date": target,
                    "predicted_qty": f.predicted,
                    "base_qty": f.base,
                    "multiplier": f.multiplier,
                    "holiday": f.holiday,
                    "history_days": f.points,
                    "model_version": MODEL_VERSION,
                    "created_at": now,
                }
            )
    await session.execute(delete(DemandForecast).where(DemandForecast.target_date < today))
    if rows:
        stmt = insert(DemandForecast)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[DemandForecast.flower_type_id, DemandForecast.target_date],
                set_={
                    c: stmt.excluded[c]
                    for c in rows[0]
                    if c not in ("flower_type_id", "target_date")
                },
            ),
            rows,
        )
    await session.commit()
    return len(rows)


async def expected_demand(
    session: AsyncSession, now: datetime, horizon_days: float
) -> dict[int, float] | None:
    """Số cành dự kiến bán trong [now, now + horizon] từ dự báo đã lưu (chia đều trong ngày).
    Trả None nếu chưa có dự báo cho hôm nay -> bộ máy giảm giá dùng cách TB 14 ngày."""
    tz = shop_tz()
    start, end = now, now + timedelta(days=horizon_days)
    first, last = start.astimezone(tz).date(), end.astimezone(tz).date()
    rows = (
        await session.execute(
            select(
                DemandForecast.flower_type_id,
                DemandForecast.target_date,
                DemandForecast.predicted_qty,
            ).where(DemandForecast.target_date >= first, DemandForecast.target_date <= last)
        )
    ).all()
    if not any(d == first for _, d, _ in rows):
        return None
    out: dict[int, float] = defaultdict(float)
    for fid, d, qty in rows:
        day_start = datetime.combine(d, datetime.min.time(), tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        overlap = (min(end, day_end) - max(start, day_start)).total_seconds()
        if overlap > 0:
            out[fid] += qty * overlap / 86400
    return dict(out)


# ============================================================ Gợi ý nhập hàng
@dataclass
class RestockLine:
    flower_type_id: int
    name: str
    cover_days: int
    forecast_total: float
    usable_stock: int
    safety_pct: int
    suggested_qty: int
    est_unit_cost: int
    est_cost: int
    holidays: list[str]


async def restock_suggestions(
    session: AsyncSession,
    now: datetime,
    import_date: date,
    cover_days: int = 4,
    safety_pct: int = 15,
) -> list[RestockLine]:
    """Lượng nên nhập vào sáng `import_date` để đủ bán `cover_days` ngày (không quá số ngày
    tươi của loại hoa), trừ tồn còn dùng được trong khoảng đó."""
    today = local_today(now)
    rules = await load_rules(session)
    history = await load_daily_sales(
        session, _history_start(today, DEFAULT_WEEKS), today - timedelta(days=1)
    )
    flowers = {
        f.id: f
        for f in (await session.scalars(select(FlowerType).where(FlowerType.is_active.is_(True))))
    }
    tz = shop_tz()
    arrival = datetime.combine(import_date, datetime.min.time(), tzinfo=tz) + timedelta(hours=6)
    last_cost = dict(
        (
            await session.execute(
                select(Batch.flower_type_id, Batch.cost_per_stem)
                .ext(distinct_on(Batch.flower_type_id))
                .order_by(Batch.flower_type_id, Batch.received_at.desc())
            )
        ).all()
    )

    out = []
    for fid, f in flowers.items():
        days = max(1, min(cover_days, f.vase_life_days))
        window_end = arrival + timedelta(days=days)
        fn = factor_fn(rules, fid)
        hist = history.get(fid, {})
        preds = [
            forecast_day(hist, today, import_date + timedelta(days=k), fn) for k in range(days)
        ]
        total = sum(p.predicted for p in preds)
        # Tồn còn dùng được: lô bán được lúc hàng mới về, tính phần còn hạn trong khoảng phủ
        usable = 0
        for b in (
            await session.scalars(
                select(Batch).where(Batch.flower_type_id == fid, *sellable_filter(arrival))
            )
        ).all():
            useful = min(b.expected_expiry_at, window_end) - arrival
            usable += math.floor(b.quantity_available * min(1.0, useful / (window_end - arrival)))
        qty = restock_quantity(total, usable, safety_pct)
        unit = last_cost.get(fid, f.reference_cost)
        out.append(
            RestockLine(
                fid,
                f.name,
                days,
                round(total, 1),
                usable,
                safety_pct,
                qty,
                unit,
                unit * qty,
                sorted({p.holiday for p in preds if p.holiday}),
            )
        )
    return sorted(out, key=lambda r: (-r.suggested_qty, r.name))


# ============================================================ Backtest
async def run_backtest(
    session: AsyncSession, now: datetime, days: int = 56, horizon: int = 7
) -> BacktestResult:
    today = local_today(now)
    rules = await load_rules(session)
    end = today - timedelta(days=1)
    first_origin = end - timedelta(days=days + horizon - 2)
    history = await load_daily_sales(session, _history_start(first_origin, DEFAULT_WEEKS), end)
    origins = [first_origin + timedelta(days=k) for k in range(days)]
    return backtest(history, rules, origins, horizon)

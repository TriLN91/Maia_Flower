"""Báo giá giỏ hàng và tạo đơn: FEFO cho cả giỏ + giữ hoa + giữ khung giờ, all-or-nothing."""

import hashlib
import secrets
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import (
    Batch,
    BatchStatus,
    BouquetTemplate,
    FlowerType,
    MovementType,
    Order,
    OrderAllocation,
    OrderItem,
    OrderStatus,
)
from app.schemas.orders import CartLineIn, CartQuoteOut, OrderCreate, QuoteLineOut
from app.services.delivery_slots import reserve_slot, shop_tz, slot_window
from app.services.inventory import apply_movement

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # bỏ 0/O, 1/I dễ nhầm khi đọc qua điện thoại


@dataclass
class PricedLine:
    template: BouquetTemplate
    quantity: int
    unit_price: int
    discount_pct: int

    @property
    def line_total(self) -> int:
        return self.unit_price * self.quantity * (100 - self.discount_pct) // 100

    @property
    def discount_amount(self) -> int:
        return self.unit_price * self.quantity - self.line_total


# =====================================================================
# Bước chung
# =====================================================================
async def _load_templates(
    session: AsyncSession, lines: Sequence[CartLineIn]
) -> dict[int, BouquetTemplate]:
    ids = [line.template_id for line in lines]
    templates = {
        t.id: t
        for t in (
            await session.scalars(
                select(BouquetTemplate)
                .options(selectinload(BouquetTemplate.items))
                .where(BouquetTemplate.id.in_(ids), BouquetTemplate.is_active.is_(True))
            )
        ).all()
    }
    missing = [i for i in ids if i not in templates]
    if missing:
        raise AppError(
            "Some bouquet templates are not available",
            code="TEMPLATE_UNAVAILABLE",
            extra={"template_ids": missing},
        )
    return templates


def _price(lines: Sequence[CartLineIn], templates: dict[int, BouquetTemplate]) -> list[PricedLine]:
    # discount_pct = 0 cho tới ngày 8 (giảm giá động)
    return [
        PricedLine(templates[line.template_id], line.quantity, templates[line.template_id].price, 0)
        for line in lines
    ]


def _flower_demand(priced: Sequence[PricedLine]) -> dict[int, int]:
    demand: dict[int, int] = defaultdict(int)
    for line in priced:
        for item in line.template.items:
            demand[item.flower_type_id] += item.quantity * line.quantity
    return dict(demand)


def _sellable_filter(deliver_by: datetime):
    """Lô bán được cho đơn giao trước `deliver_by`: đang hoạt động, còn hàng, chưa bị đánh
    giá héo hẳn, và còn hạn tới lúc giao xong."""
    return (
        Batch.status == BatchStatus.ACTIVE,
        Batch.quantity_available > 0,
        Batch.expected_expiry_at > deliver_by,
        or_(Batch.freshness_override.is_(None), Batch.freshness_override > 0),
    )


# =====================================================================
# Báo giá (không giữ gì)
# =====================================================================
async def quote_cart(
    session: AsyncSession, lines: Sequence[CartLineIn], now: datetime
) -> CartQuoteOut:
    templates = await _load_templates(session, lines)
    priced = _price(lines, templates)
    demand = _flower_demand(priced)

    stock = dict(
        (
            await session.execute(
                select(Batch.flower_type_id, func.sum(Batch.quantity_available))
                .where(Batch.flower_type_id.in_(demand), *_sellable_filter(now))
                .group_by(Batch.flower_type_id)
            )
        ).all()
    )
    short_flowers = {fid for fid, need in demand.items() if stock.get(fid, 0) < need}

    out_lines = [
        QuoteLineOut(
            template_id=p.template.id,
            name=p.template.name,
            quantity=p.quantity,
            unit_price=p.unit_price,
            discount_pct=p.discount_pct,
            line_total=p.line_total,
            available=not any(i.flower_type_id in short_flowers for i in p.template.items),
        )
        for p in priced
    ]
    subtotal = sum(p.unit_price * p.quantity for p in priced)
    discount = sum(p.discount_amount for p in priced)
    fee = get_settings().flat_delivery_fee
    return CartQuoteOut(
        lines=out_lines,
        subtotal=subtotal,
        discount_total=discount,
        delivery_fee=fee,
        total=subtotal - discount + fee,
        all_available=not short_flowers,
    )


# =====================================================================
# Tạo đơn
# =====================================================================
def fingerprint(data: OrderCreate) -> str:
    return hashlib.sha256(data.model_dump_json().encode()).hexdigest()


async def _replay(session: AsyncSession, key: str, fp: str) -> Order | None:
    existing = await session.scalar(select(Order.id).where(Order.idempotency_key == key))
    if existing is None:
        return None
    order = await get_order(session, existing)
    if order.request_fingerprint != fp:
        raise AppError(
            "Idempotency-Key was already used with a different request",
            code="IDEMPOTENCY_KEY_REUSED",
            status_code=422,
        )
    return order


async def _new_code(session: AsyncSession, now: datetime) -> str:
    day = now.astimezone(shop_tz()).strftime("%y%m%d")
    for _ in range(10):
        code = f"MF-{day}-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
        if await session.scalar(select(Order.id).where(Order.code == code)) is None:
            return code
    raise ConflictError("Could not allocate an order code, please retry", code="RETRY")


async def _lock_batches(
    session: AsyncSession, flower_ids: Sequence[int], deliver_by: datetime
) -> dict[int, list[Batch]]:
    """Khóa mọi lô bán được của các loại hoa cần dùng, theo thứ tự cố định
    (loại hoa, hạn dùng, id). Mọi giao dịch khóa theo cùng thứ tự -> không deadlock;
    thứ tự hạn dùng tăng dần cũng chính là thứ tự FEFO."""
    batches = (
        await session.scalars(
            select(Batch)
            .where(Batch.flower_type_id.in_(flower_ids), *_sellable_filter(deliver_by))
            .order_by(Batch.flower_type_id, Batch.expected_expiry_at, Batch.id)
            .with_for_update(of=Batch)
            .execution_options(populate_existing=True)
        )
    ).all()
    grouped: dict[int, list[Batch]] = defaultdict(list)
    for b in batches:
        grouped[b.flower_type_id].append(b)
    return grouped


async def _raise_shortage(
    session: AsyncSession, demand: dict[int, int], grouped: dict[int, list[Batch]]
) -> None:
    shortages = {
        fid: (need, sum(b.quantity_available for b in grouped.get(fid, [])))
        for fid, need in demand.items()
    }
    shortages = {fid: v for fid, v in shortages.items() if v[1] < v[0]}
    if not shortages:
        return
    names = dict(
        (
            await session.execute(
                select(FlowerType.id, FlowerType.name).where(FlowerType.id.in_(shortages))
            )
        ).all()
    )
    raise ConflictError(
        "Not enough fresh flowers for this order",
        code="OUT_OF_STOCK",
        extra={
            "shortages": [
                {"flower_type_id": fid, "name": names.get(fid), "needed": need, "available": have}
                for fid, (need, have) in sorted(shortages.items())
            ]
        },
    )


async def create_order(
    session: AsyncSession, data: OrderCreate, idempotency_key: str, now: datetime
) -> tuple[Order, bool]:
    """Trả về (đơn, có_phải_gửi_lại). Toàn bộ trong một transaction: thiếu bất kỳ thứ gì
    (khung giờ, một loại hoa) thì không có gì bị giữ."""
    fp = fingerprint(data)
    if (replayed := await _replay(session, idempotency_key, fp)) is not None:
        return replayed, True

    templates = await _load_templates(session, data.items)
    priced = _price(data.items, templates)
    demand = _flower_demand(priced)

    # 1) Khung giờ trước (khóa 1 dòng), 2) rồi tới các lô — cùng thứ tự ở mọi giao dịch
    slot_day = await reserve_slot(session, data.slot_id, data.delivery_date, now)
    starts_at, ends_at = slot_window(slot_day.slot, data.delivery_date)

    grouped = await _lock_batches(session, sorted(demand), ends_at)
    await _raise_shortage(session, demand, grouped)

    subtotal = sum(p.unit_price * p.quantity for p in priced)
    discount = sum(p.discount_amount for p in priced)
    fee = get_settings().flat_delivery_fee
    order = Order(
        code=await _new_code(session, now),
        tracking_token=secrets.token_urlsafe(32),
        idempotency_key=idempotency_key,
        request_fingerprint=fp,
        status=OrderStatus.PENDING_PAYMENT,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        recipient_name=data.recipient_name,
        recipient_phone=data.recipient_phone,
        delivery_address=data.delivery_address,
        delivery_lat=data.delivery_lat,
        delivery_lng=data.delivery_lng,
        delivery_slot_day_id=slot_day.id,
        delivery_starts_at=starts_at,
        delivery_ends_at=ends_at,
        card_message=data.card_message,
        note=data.note,
        subtotal=subtotal,
        discount_total=discount,
        delivery_fee=fee,
        total=subtotal - discount + fee,
        hold_expires_at=now + timedelta(minutes=get_settings().hold_minutes),
        items=[
            OrderItem(
                template_id=p.template.id,
                template_name=p.template.name,
                quantity=p.quantity,
                unit_price=p.unit_price,
                discount_pct=p.discount_pct,
                line_total=p.line_total,
            )
            for p in priced
        ],
    )
    try:
        # Mọi lệnh ghi nằm trong khối này: khi 2 request cùng Idempotency-Key chạy song song,
        # request sau đụng UNIQUE ngay lúc flush -> rollback và trả lại đơn của request đầu.
        session.add(order)
        await session.flush()  # cần id của đơn và các dòng

        # Phân bổ FEFO: mỗi loại hoa là một hàng đợi lô theo hạn dùng tăng dần
        queues = {fid: deque(batches) for fid, batches in grouped.items()}
        remaining = {b.id: b.quantity_available for bs in grouped.values() for b in bs}
        taken: dict[int, int] = defaultdict(int)  # batch_id -> tổng cành lấy
        batch_by_id = {b.id: b for bs in grouped.values() for b in bs}

        for order_item, line in zip(order.items, priced, strict=True):
            for recipe in line.template.items:
                need = recipe.quantity * line.quantity
                queue = queues[recipe.flower_type_id]
                while need:
                    batch = queue[0]
                    take = min(need, remaining[batch.id])
                    # add trực tiếp (không qua order_item.allocations): sau flush, đụng vào quan hệ
                    # sẽ kích hoạt lazy-load — không được phép với async.
                    session.add(
                        OrderAllocation(
                            order_item_id=order_item.id,
                            batch_id=batch.id,
                            flower_type_id=recipe.flower_type_id,
                            quantity=take,
                        )
                    )
                    remaining[batch.id] -= take
                    taken[batch.id] += take
                    need -= take
                    if remaining[batch.id] == 0:
                        queue.popleft()

        for batch_id, qty in sorted(taken.items()):
            await apply_movement(
                session,
                batch_by_id[batch_id],
                MovementType.RESERVE,
                -qty,
                reason=f"Order {order.code}",
                order_id=order.id,
            )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if (replayed := await _replay(session, idempotency_key, fp)) is not None:
            return replayed, True
        raise
    return await get_order(session, order.id), False


# =====================================================================
# Đọc đơn
# =====================================================================
def _order_query():
    return (
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.allocations))
        .execution_options(populate_existing=True)
    )


async def get_order(session: AsyncSession, order_id: int) -> Order:
    order = await session.scalar(_order_query().where(Order.id == order_id))
    if order is None:
        raise NotFoundError("Order not found")
    return order


async def get_order_by_token(session: AsyncSession, token: str) -> Order:
    order = await session.scalar(_order_query().where(Order.tracking_token == token))
    if order is None:
        raise NotFoundError("Order not found")
    return order

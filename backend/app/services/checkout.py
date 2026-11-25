"""Báo giá giỏ hàng và tạo đơn: FEFO cho cả giỏ + giữ hoa + giữ khung giờ, all-or-nothing."""

import hashlib
import secrets
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import (
    Batch,
    BouquetTemplate,
    Order,
    OrderItem,
    OrderStatus,
)
from app.schemas.orders import CartLineIn, CartQuoteOut, OrderCreate, QuoteLineOut
from app.services.delivery_fee import compute_fee
from app.services.delivery_quote import verify_quote
from app.services.delivery_slots import reserve_slot, shop_tz, slot_window
from app.services.order_workflow import record_event
from app.services.pricing import current_discounts
from app.services.reservations import Need, allocate_and_reserve, sellable_filter
from app.services.shop_settings import get_delivery_settings

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


async def _price(
    session: AsyncSession, lines: Sequence[CartLineIn], templates: dict[int, BouquetTemplate]
) -> list[PricedLine]:
    """Giá = giá mẫu (chủ shop nhập) − mức giảm động đang áp dụng (bộ máy "Cần bán gấp")."""
    discounts = await current_discounts(session, templates)
    return [
        PricedLine(
            templates[line.template_id],
            line.quantity,
            templates[line.template_id].price,
            discounts.get(line.template_id, 0),
        )
        for line in lines
    ]


def _flower_demand(priced: Sequence[PricedLine]) -> dict[int, int]:
    demand: dict[int, int] = defaultdict(int)
    for line in priced:
        for item in line.template.items:
            demand[item.flower_type_id] += item.quantity * line.quantity
    return dict(demand)


# =====================================================================
# Báo giá (không giữ gì)
# =====================================================================
async def quote_cart(
    session: AsyncSession,
    lines: Sequence[CartLineIn],
    now: datetime,
    *,
    delivery_quote_token: str | None = None,
    delivery_date: date | None = None,
) -> CartQuoteOut:
    templates = await _load_templates(session, lines)
    priced = await _price(session, lines, templates)
    demand = _flower_demand(priced)

    stock = dict(
        (
            await session.execute(
                select(Batch.flower_type_id, func.sum(Batch.quantity_available))
                .where(Batch.flower_type_id.in_(demand), *sellable_filter(now))
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
    fee = None
    if delivery_quote_token:
        claims = verify_quote(delivery_quote_token)
        fee = compute_fee(
            claims.distance_km,
            settings=await get_delivery_settings(session),
            delivery_date=delivery_date,
            subtotal=subtotal - discount,
        ).total
    return CartQuoteOut(
        lines=out_lines,
        subtotal=subtotal,
        discount_total=discount,
        delivery_fee=fee,
        total=subtotal - discount + (fee or 0),
        all_available=not short_flowers,
    )


# =====================================================================
# Tạo đơn
# =====================================================================
def fingerprint(data: OrderCreate) -> str:
    """Dấu vân tay nội dung đơn để phát hiện dùng lại Idempotency-Key cho đơn KHÁC.

    Bỏ `delivery_quote_token`: token được ký lại mỗi lần lấy báo giá (iat/exp đổi theo giây),
    nên khách lấy lại báo giá rồi bấm đặt lần nữa vẫn là CÙNG một đơn.
    """
    payload = data.model_dump_json(exclude={"delivery_quote_token"})
    return hashlib.sha256(payload.encode()).hexdigest()


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


async def create_order(
    session: AsyncSession, data: OrderCreate, idempotency_key: str, now: datetime
) -> tuple[Order, bool]:
    """Trả về (đơn, có_phải_gửi_lại). Toàn bộ trong một transaction: thiếu bất kỳ thứ gì
    (khung giờ, một loại hoa) thì không có gì bị giữ."""
    fp = fingerprint(data)
    if (replayed := await _replay(session, idempotency_key, fp)) is not None:
        return replayed, True

    # Kiểm tra báo giá ship TRƯỚC khi khóa bất cứ thứ gì (lỗi rẻ thì báo sớm)
    quote = verify_quote(data.delivery_quote_token)
    templates = await _load_templates(session, data.items)
    priced = await _price(session, data.items, templates)
    subtotal = sum(p.unit_price * p.quantity for p in priced)
    discount = sum(p.discount_amount for p in priced)
    fee = compute_fee(
        quote.distance_km,
        settings=await get_delivery_settings(session),
        delivery_date=data.delivery_date,
        subtotal=subtotal - discount,
    ).total

    # Khung giờ khóa trước, các lô khóa sau — cùng thứ tự ở mọi giao dịch (xem reservations.py)
    slot_day = await reserve_slot(session, data.slot_id, data.delivery_date, now)
    starts_at, ends_at = slot_window(slot_day.slot, data.delivery_date)

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
        delivery_lat=quote.lat,
        delivery_lng=quote.lng,
        delivery_distance_km=quote.distance_km,
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

        await allocate_and_reserve(
            session,
            order_id=order.id,
            order_code=order.code,
            needs=[
                Need(order_item.id, recipe.flower_type_id, recipe.quantity * line.quantity)
                for order_item, line in zip(order.items, priced, strict=True)
                for recipe in line.template.items
            ],
            deliver_by=ends_at,
        )
        record_event(session, order, OrderStatus.PENDING_PAYMENT, actor="customer")
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
        .options(
            selectinload(Order.items).selectinload(OrderItem.allocations),
            selectinload(Order.events),
            selectinload(Order.payments),
        )
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

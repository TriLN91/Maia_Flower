from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status

from app.api.deps import SessionDep
from app.core.rate_limit import enforce, limit_by_ip
from app.models import Order
from app.schemas.orders import (
    CartQuoteIn,
    CartQuoteOut,
    OrderCreate,
    OrderCreatedOut,
    OrderPublicOut,
    SlotAvailabilityOut,
)
from app.services import checkout, delivery_slots
from app.services.inventory import utcnow

router = APIRouter(prefix="/shop", tags=["shop: checkout"])


def public_order(order: Order, *, with_token: bool = False) -> OrderPublicOut:
    schema = OrderCreatedOut if with_token else OrderPublicOut
    return schema.model_validate(order)


@router.post(
    "/cart/quote", response_model=CartQuoteOut, dependencies=[limit_by_ip("cart-quote", 60, 60)]
)
async def quote_cart(session: SessionDep, body: CartQuoteIn) -> CartQuoteOut:
    """Tính lại giỏ hàng từ dữ liệu server (giá, còn hàng, phí ship nếu có quote token).
    Không giữ hoa."""
    return await checkout.quote_cart(
        session,
        body.items,
        utcnow(),
        delivery_quote_token=body.delivery_quote_token,
        delivery_date=body.delivery_date,
    )


@router.get("/delivery-slots", response_model=list[SlotAvailabilityOut])
async def delivery_slot_availability(
    session: SessionDep, day: Annotated[date, Query(alias="date")]
) -> list[SlotAvailabilityOut]:
    rows = await delivery_slots.availability(session, day, utcnow())
    return [
        SlotAvailabilityOut(
            slot_id=r.slot.id,
            date=r.day,
            start_time=r.slot.start_time,
            end_time=r.slot.end_time,
            capacity=r.capacity,
            remaining=r.remaining,
            bookable=r.bookable,
            reason=r.reason,
        )
        for r in rows
    ]


@router.post(
    "/orders",
    dependencies=[limit_by_ip("order-create", 20, 60)],
    response_model=OrderCreatedOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Gửi lại cùng Idempotency-Key: trả về đơn đã tạo"},
        409: {"description": "OUT_OF_STOCK hoặc SLOT_FULL"},
    },
)
async def create_order(
    session: SessionDep,
    body: OrderCreate,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=100,
            description="Chuỗi ngẫu nhiên do client tạo cho mỗi lần đặt (vd. UUID). "
            "Gửi lại cùng key sẽ nhận lại đúng đơn cũ, không tạo đơn mới.",
        ),
    ],
) -> OrderPublicOut:
    """Tạo đơn: giữ hoa (FEFO) và giữ khung giờ trong 15 phút chờ thanh toán."""
    # Chống đơn ảo giữ hết hoa: mỗi số điện thoại tối đa 5 lần đặt / 10 phút
    await enforce(f"order-create:phone:{body.customer_phone}", 5, 10 * 60)
    order, replayed = await checkout.create_order(session, body, idempotency_key, utcnow())
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return public_order(order, with_token=True)


@router.get(
    "/orders/track/{token}",
    response_model=OrderPublicOut,
    dependencies=[limit_by_ip("order-track", 30, 60)],
)
async def track_order(session: SessionDep, token: str) -> OrderPublicOut:
    return public_order(await checkout.get_order_by_token(session, token))

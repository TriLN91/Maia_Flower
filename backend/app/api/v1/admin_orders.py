from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentStaff, SessionDep
from app.models import Order, OrderItem, OrderStatus
from app.schemas.common import Page
from app.schemas.orders import OrderAdminOut, OrderSummaryOut, TransitionIn
from app.services import checkout, order_workflow
from app.services.delivery_slots import shop_tz

router = APIRouter(prefix="/admin/orders", tags=["admin: orders"])


@router.get("", response_model=Page[OrderSummaryOut])
async def list_orders(
    session: SessionDep,
    _: CurrentStaff,
    status: OrderStatus | None = None,
    delivery_date: Annotated[date | None, Query(description="Ngày giao (giờ VN)")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[OrderSummaryOut]:
    """Danh sách đơn, sắp theo giờ giao gần nhất — thợ bó xem việc trong ngày."""
    conditions = []
    if status is not None:
        conditions.append(Order.status == status)
    if delivery_date is not None:
        start = datetime.combine(delivery_date, time.min, tzinfo=shop_tz())
        conditions += [
            Order.delivery_starts_at >= start,
            Order.delivery_starts_at < start + timedelta(days=1),
        ]

    total = await session.scalar(select(func.count()).select_from(Order).where(*conditions))
    item_count = (
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .where(OrderItem.order_id == Order.id)
        .correlate(Order)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(Order, item_count.label("item_count"))
            .where(*conditions)
            .order_by(Order.delivery_starts_at, Order.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return Page(
        items=[
            OrderSummaryOut(
                id=o.id,
                code=o.code,
                status=o.status,
                customer_name=o.customer_name,
                delivery_starts_at=o.delivery_starts_at,
                delivery_ends_at=o.delivery_ends_at,
                total=o.total,
                item_count=count,
                created_at=o.created_at,
            )
            for o, count in rows
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{order_id}", response_model=OrderAdminOut)
async def get_order(session: SessionDep, _: CurrentStaff, order_id: int) -> Order:
    """Chi tiết đơn: phân bổ lô (lấy hoa ở đâu), lịch sử trạng thái, các lần thanh toán."""
    return await checkout.get_order(session, order_id)


@router.post("/{order_id}/transition", response_model=OrderAdminOut)
async def transition(
    session: SessionDep, user: CurrentStaff, order_id: int, body: TransitionIn
) -> Order:
    """Chuyển trạng thái theo quy trình:
    paid → preparing → delivering → completed (thợ bó);
    hủy đơn chờ thanh toán / đơn đã trả tiền, xác nhận đã hoàn tiền (chủ shop)."""
    await order_workflow.transition(session, user, order_id, body.to_status, body.note)
    return await checkout.get_order(session, order_id)

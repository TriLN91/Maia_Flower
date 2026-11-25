"""Vòng đời đơn hàng (state machine) và job nhả đơn quá hạn giữ chỗ."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models import (
    Order,
    OrderEvent,
    OrderStatus,
    Payment,
    PaymentStatus,
    StaffRole,
    StaffUser,
)
from app.services.reservations import release_holdings

log = logging.getLogger(__name__)
S = OrderStatus


@dataclass(frozen=True)
class Rule:
    owner_only: bool = False
    release_stock: bool = False  # trả hoa + khung giờ khi chuyển
    mark_refund: bool = False  # đánh dấu khoản đã thu cần hoàn


# Chỉ những bước chuyển này hợp lệ khi nhân viên thao tác (thanh toán / hết hạn do hệ thống làm)
STAFF_TRANSITIONS: dict[tuple[OrderStatus, OrderStatus], Rule] = {
    (S.PAID, S.PREPARING): Rule(),
    (S.PREPARING, S.DELIVERING): Rule(),
    (S.DELIVERING, S.COMPLETED): Rule(),
    # Hủy đơn chưa thanh toán: nhả hoa + khung giờ ngay, không phải đợi hết 15 phút
    (S.PENDING_PAYMENT, S.CANCELLED): Rule(owner_only=True, release_stock=True),
    # Hủy đơn đã thanh toán (chưa bó): nhả hàng, chờ hoàn tiền
    (S.PAID, S.NEEDS_REFUND): Rule(owner_only=True, release_stock=True, mark_refund=True),
    # Đã hoàn tiền xong
    (S.NEEDS_REFUND, S.CANCELLED): Rule(owner_only=True),
}


async def lock_order(session: AsyncSession, order_id: int) -> Order:
    order = await session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update(of=Order)
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundError("Order not found")
    return order


def record_event(
    session: AsyncSession,
    order: Order,
    to_status: OrderStatus,
    *,
    actor: str,
    actor_id: int | None = None,
    note: str | None = None,
    from_status: OrderStatus | None = None,
) -> None:
    session.add(
        OrderEvent(
            order_id=order.id,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            actor_id=actor_id,
            note=note,
        )
    )


def set_status(
    session: AsyncSession,
    order: Order,
    to_status: OrderStatus,
    *,
    actor: str,
    actor_id: int | None = None,
    note: str | None = None,
) -> None:
    record_event(
        session,
        order,
        to_status,
        actor=actor,
        actor_id=actor_id,
        note=note,
        from_status=order.status,
    )
    order.status = to_status
    if to_status != S.PENDING_PAYMENT:
        order.hold_expires_at = None


async def transition(
    session: AsyncSession,
    user: StaffUser,
    order_id: int,
    to_status: OrderStatus,
    note: str | None = None,
) -> None:
    order = await lock_order(session, order_id)
    rule = STAFF_TRANSITIONS.get((order.status, to_status))
    if rule is None:
        allowed = sorted(t.value for (f, t) in STAFF_TRANSITIONS if f == order.status)
        raise AppError(
            f"Cannot change order from {order.status.value} to {to_status.value}",
            code="INVALID_TRANSITION",
            extra={"from": order.status.value, "allowed": allowed},
        )
    if rule.owner_only and user.role != StaffRole.OWNER:
        raise AppError("Owner permission required", code="FORBIDDEN", status_code=403)

    if rule.release_stock:
        await release_holdings(session, order)
    if rule.mark_refund:
        await session.execute(
            update(Payment)
            .where(Payment.order_id == order.id, Payment.status == PaymentStatus.SUCCEEDED)
            .values(needs_refund=True)
        )
    set_status(session, order, to_status, actor="staff", actor_id=user.id, note=note)
    await session.commit()


async def expire_overdue_orders(session: AsyncSession, now: datetime, limit: int = 100) -> int:
    """Nhả hoa + khung giờ của các đơn chờ thanh toán đã quá hạn giữ chỗ.

    Mỗi đơn một transaction; `SKIP LOCKED` để nhiều worker chạy song song không giẫm chân nhau
    và không chờ đơn đang được IPN xử lý (IPN giữ khóa đơn đó).
    """
    ids = (
        await session.scalars(
            select(Order.id)
            .where(Order.status == S.PENDING_PAYMENT, Order.hold_expires_at < now)
            .order_by(Order.hold_expires_at)
            .limit(limit)
        )
    ).all()
    expired = 0
    for order_id in ids:
        order = await session.scalar(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update(of=Order, skip_locked=True)
            .execution_options(populate_existing=True)
        )
        # Đơn có thể vừa được thanh toán / đang bị xử lý ở nơi khác -> bỏ qua
        if order is None or order.status != S.PENDING_PAYMENT or order.hold_expires_at >= now:
            await session.rollback()
            continue
        await release_holdings(session, order)
        set_status(session, order, S.EXPIRED, actor="system", note="Payment hold expired")
        await session.commit()
        expired += 1
    if expired:
        log.info("Expired %d unpaid orders", expired)
    return expired

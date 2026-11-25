"""Luồng thanh toán: tạo giao dịch, xử lý IPN (server-to-server), đọc kết quả return URL.

Nguyên tắc (giống VNPay): CHỈ IPN được đổi trạng thái đơn. Return URL đi qua trình duyệt của
khách nên chỉ dùng để hiển thị — dù có chữ ký hợp lệ cũng không cập nhật DB.
"""

import logging
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import Order, OrderStatus, Payment, PaymentStatus
from app.services.order_workflow import lock_order, set_status
from app.services.payments.provider import get_provider
from app.services.reservations import reserve_again

log = logging.getLogger(__name__)


# Mã phản hồi IPN theo quy ước VNPay (cổng sẽ gửi lại IPN nếu không nhận được "00"/"02")
@dataclass(frozen=True)
class IpnResponse:
    RspCode: str
    Message: str


IPN_OK = IpnResponse("00", "Confirm Success")
IPN_ALREADY = IpnResponse("02", "Order already confirmed")
IPN_NOT_FOUND = IpnResponse("01", "Order not found")
IPN_BAD_AMOUNT = IpnResponse("04", "Invalid amount")
IPN_BAD_SIGNATURE = IpnResponse("97", "Invalid signature")
IPN_BAD_REQUEST = IpnResponse("99", "Invalid request")


@dataclass(frozen=True)
class PaymentStart:
    payment_url: str
    txn_ref: str
    amount: int
    expires_at: datetime


async def start_payment(session: AsyncSession, tracking_token: str, now: datetime) -> PaymentStart:
    order = await session.scalar(
        select(Order)
        .where(Order.tracking_token == tracking_token)
        .with_for_update(of=Order)
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundError("Order not found")
    if order.status != OrderStatus.PENDING_PAYMENT or order.hold_expires_at is None:
        raise ConflictError(
            "Order is not awaiting payment",
            code="ORDER_NOT_PAYABLE",
            extra={"status": order.status.value},
        )
    if order.hold_expires_at <= now:
        raise ConflictError("Payment hold has expired", code="HOLD_EXPIRED")

    provider = get_provider()
    # Mỗi lần bấm "Thanh toán" là một giao dịch mới (khách có thể thử lại sau khi thất bại)
    txn_ref = f"{order.code}-{secrets.token_hex(3).upper()}"
    session.add(
        Payment(order_id=order.id, provider=provider.name, txn_ref=txn_ref, amount=order.total)
    )
    url = provider.payment_url(
        txn_ref=txn_ref,
        amount=order.total,
        order_info=f"Thanh toan don hang {order.code}",
        now=now,
        expires_at=order.hold_expires_at,
    )
    expires_at = order.hold_expires_at
    await session.commit()
    return PaymentStart(url, txn_ref, order.total, expires_at)


async def handle_ipn(
    session: AsyncSession, params: Mapping[str, str], now: datetime
) -> IpnResponse:
    """Idempotent: cổng gửi lại cùng IPN bao nhiêu lần cũng chỉ ghi nhận một lần."""
    provider = get_provider()
    if not provider.verify(params):
        log.warning("IPN with invalid signature: %s", params.get("vnp_TxnRef"))
        return IPN_BAD_SIGNATURE
    try:
        result = provider.parse(params)
    except (KeyError, ValueError):
        return IPN_BAD_REQUEST

    # Khóa giao dịch trước, rồi tới đơn (cùng thứ tự với mọi nơi khác)
    payment = await session.scalar(
        select(Payment)
        .where(Payment.txn_ref == result.txn_ref)
        .with_for_update(of=Payment)
        .execution_options(populate_existing=True)
    )
    if payment is None:
        return IPN_NOT_FOUND
    if result.amount != payment.amount:
        log.error(
            "IPN amount mismatch for %s: %s != %s", payment.txn_ref, result.amount, payment.amount
        )
        return IPN_BAD_AMOUNT
    if payment.status != PaymentStatus.PENDING:
        return IPN_ALREADY

    order = await lock_order(session, payment.order_id)
    payment.response_code = result.response_code
    payment.gateway_txn_no = result.gateway_txn_no
    payment.raw_callback = dict(params)

    if not result.success:
        payment.status = (
            PaymentStatus.CANCELLED if result.cancelled_by_customer else PaymentStatus.FAILED
        )
        # Đơn vẫn chờ thanh toán: khách thử lại được tới khi hết hạn giữ chỗ
        await session.commit()
        return IPN_OK

    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = now

    if order.status == OrderStatus.PENDING_PAYMENT:
        set_status(session, order, OrderStatus.PAID, actor="payment", note=payment.txn_ref)
    elif order.status == OrderStatus.EXPIRED:
        # Tiền về sau khi đã nhả giữ chỗ: thử giữ lại hoa + khung giờ
        try:
            async with session.begin_nested():  # SAVEPOINT: thất bại thì chỉ hoàn tác phần này
                await reserve_again(session, order, now)
            set_status(
                session,
                order,
                OrderStatus.PAID,
                actor="payment",
                note=f"{payment.txn_ref}: late payment, stock re-reserved",
            )
        except AppError as e:
            payment.needs_refund = True
            set_status(
                session,
                order,
                OrderStatus.NEEDS_REFUND,
                actor="payment",
                note=f"{payment.txn_ref}: late payment, cannot re-reserve ({e.code})",
            )
    else:
        # Đơn đã được trả bằng giao dịch khác / đã bị hủy -> khoản này phải hoàn
        payment.needs_refund = True
        log.warning("Extra payment %s for order %s (%s)", payment.txn_ref, order.code, order.status)

    await session.commit()
    return IPN_OK


@dataclass(frozen=True)
class ReturnInfo:
    order_code: str
    payment_status: PaymentStatus
    order_status: OrderStatus
    gateway_success: bool


async def describe_return(session: AsyncSession, params: Mapping[str, str]) -> ReturnInfo:
    """Chỉ đọc. Trạng thái thật lấy từ DB (do IPN cập nhật), không lấy từ tham số URL."""
    provider = get_provider()
    if not provider.verify(params):
        raise AppError("Invalid signature", code="INVALID_SIGNATURE")
    result = provider.parse(params)
    row = (
        await session.execute(
            select(Payment, Order)
            .join(Order, Order.id == Payment.order_id)
            .where(Payment.txn_ref == result.txn_ref)
        )
    ).first()
    if row is None:
        raise NotFoundError("Payment not found")
    payment, order = row
    return ReturnInfo(order.code, payment.status, order.status, result.success)

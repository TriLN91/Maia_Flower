from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.core.rate_limit import limit_by_ip
from app.models import OrderStatus, PaymentStatus
from app.services.inventory import utcnow
from app.services.payments import service

router = APIRouter(tags=["payments"])


class PayOut(BaseModel):
    payment_url: str
    txn_ref: str
    amount: int
    expires_at: datetime


class IpnOut(BaseModel):
    RspCode: str
    Message: str


class ReturnOut(BaseModel):
    order_code: str
    payment_status: PaymentStatus
    order_status: OrderStatus
    gateway_success: bool
    message: str


@router.post(
    "/shop/orders/track/{token}/pay",
    response_model=PayOut,
    tags=["shop: checkout"],
    dependencies=[limit_by_ip("pay-start", 10, 60)],
)
async def start_payment(session: SessionDep, token: str) -> PayOut:
    """Tạo giao dịch và trả về URL cổng thanh toán. Cần tracking token (chỉ người đặt có)."""
    start = await service.start_payment(session, token, utcnow())
    return PayOut(**start.__dict__)


@router.get("/payments/mock/ipn", response_model=IpnOut)
async def mock_ipn(session: SessionDep, request: Request) -> IpnOut:
    """IPN (server-to-server) từ cổng thanh toán. Luôn trả 200 + RspCode theo quy ước VNPay."""
    result = await service.handle_ipn(session, dict(request.query_params), utcnow())
    return IpnOut(RspCode=result.RspCode, Message=result.Message)


@router.get("/payments/mock/return", response_model=ReturnOut)
async def mock_return(session: SessionDep, request: Request) -> ReturnOut:
    """Trình duyệt quay về sau khi thanh toán. Chỉ hiển thị — trạng thái do IPN quyết định."""
    info = await service.describe_return(session, dict(request.query_params))
    if info.order_status == OrderStatus.PAID:
        message = "Thanh toán thành công, shop đã nhận đơn."
    elif info.gateway_success:
        message = "Cổng báo thành công, shop đang xác nhận thanh toán."
    else:
        message = "Thanh toán chưa thành công, bạn có thể thử lại trước khi hết hạn giữ hoa."
    return ReturnOut(**info.__dict__, message=message)

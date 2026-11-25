"""Cổng thanh toán. Logic đơn hàng chỉ làm việc với `PaymentProvider`; đổi từ mock sang VNPay
thật chỉ cần thêm một lớp mới (khác URL cổng và khóa), không sửa luồng đơn."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.services.payments import signing

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SUCCESS_CODE = "00"
CUSTOMER_CANCELLED_CODE = "24"


@dataclass(frozen=True)
class CallbackResult:
    txn_ref: str
    amount: int  # VNĐ (đã chia 100)
    response_code: str
    transaction_status: str
    gateway_txn_no: str | None

    @property
    def success(self) -> bool:
        return self.response_code == SUCCESS_CODE and self.transaction_status == SUCCESS_CODE

    @property
    def cancelled_by_customer(self) -> bool:
        return self.response_code == CUSTOMER_CANCELLED_CODE


class PaymentProvider(Protocol):
    name: str

    def payment_url(
        self, *, txn_ref: str, amount: int, order_info: str, now: datetime, expires_at: datetime
    ) -> str: ...

    def verify(self, params: Mapping[str, str]) -> bool: ...

    def parse(self, params: Mapping[str, str]) -> CallbackResult: ...


def vnp_time(dt: datetime) -> str:
    return dt.astimezone(VN).strftime("%Y%m%d%H%M%S")


class MockProvider:
    """Cổng giả lập chạy ngay trong app (`/mock-gateway`), dùng đúng định dạng tham số và
    chữ ký của VNPay — nên code xác minh chữ ký / idempotency / kiểm tra số tiền là code thật."""

    name = "mock"
    TMN_CODE = "MAIAMOCK"

    def __init__(self, secret: str, public_base_url: str):
        self.secret = secret
        self.base = public_base_url.rstrip("/")

    def payment_url(
        self, *, txn_ref: str, amount: int, order_info: str, now: datetime, expires_at: datetime
    ) -> str:
        params = {
            "vnp_Version": "2.1.0",
            "vnp_Command": "pay",
            "vnp_TmnCode": self.TMN_CODE,
            "vnp_Amount": str(amount * 100),  # VNPay tính theo đơn vị 1/100 đồng
            "vnp_CurrCode": "VND",
            "vnp_TxnRef": txn_ref,
            "vnp_OrderInfo": order_info,
            "vnp_OrderType": "other",
            "vnp_Locale": "vn",
            "vnp_ReturnUrl": f"{self.base}/api/v1/payments/mock/return",
            "vnp_IpAddr": "127.0.0.1",
            "vnp_CreateDate": vnp_time(now),
            "vnp_ExpireDate": vnp_time(expires_at),
        }
        return f"{self.base}/mock-gateway/pay?{signing.signed_query(params, self.secret)}"

    def verify(self, params: Mapping[str, str]) -> bool:
        return signing.verify(params, self.secret)

    def parse(self, params: Mapping[str, str]) -> CallbackResult:
        return CallbackResult(
            txn_ref=params["vnp_TxnRef"],
            amount=int(params["vnp_Amount"]) // 100,
            response_code=params.get("vnp_ResponseCode", ""),
            transaction_status=params.get("vnp_TransactionStatus", ""),
            gateway_txn_no=params.get("vnp_TransactionNo"),
        )


def get_provider() -> PaymentProvider:
    s = get_settings()
    return MockProvider(s.mock_pay_secret, s.public_base_url)

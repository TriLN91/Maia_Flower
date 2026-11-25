"""Cổng thanh toán GIẢ LẬP (đóng vai VNPay) — chỉ bật khi PAYMENT_PROVIDER=mock và không phải
production. Nằm ngoài /api/v1 vì về mặt khái niệm đây là "hệ thống bên ngoài".

Luồng: shop redirect khách tới /mock-gateway/pay?…(đã ký) -> khách bấm một nút -> cổng gửi IPN
về shop (server-to-server) rồi redirect trình duyệt về return URL — y như cổng thật.
"""

import html
import logging
import secrets
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.db import SessionLocal
from app.core.errors import AppError
from app.services.inventory import utcnow
from app.services.payments import signing
from app.services.payments.provider import VN, get_provider, vnp_time
from app.services.payments.service import handle_ipn

log = logging.getLogger(__name__)
router = APIRouter(prefix="/mock-gateway", tags=["mock payment gateway"], include_in_schema=True)

Outcome = Literal["success", "failed", "cancelled", "success_late_ipn", "success_duplicate_ipn"]
OUTCOMES: dict[str, str] = {
    "success": "✅ Thanh toán thành công",
    "failed": "❌ Thất bại (không đủ số dư)",
    "cancelled": "↩️ Khách hủy giao dịch",
    "success_late_ipn": "⏳ Thành công, IPN đến trễ 2 phút",
    "success_duplicate_ipn": "🔁 Thành công, IPN gửi 2 lần",
}
RESPONSE_CODES = {"success": "00", "failed": "51", "cancelled": "24"}


def _verified_request(params: dict[str, str]) -> dict[str, str]:
    provider = get_provider()
    if not provider.verify(params):
        raise AppError("Invalid payment request signature", code="INVALID_SIGNATURE")
    expire = datetime.strptime(params["vnp_ExpireDate"], "%Y%m%d%H%M%S").replace(tzinfo=VN)
    if expire < utcnow():
        raise AppError("Payment request has expired", code="PAYMENT_REQUEST_EXPIRED")
    return params


@router.get("/pay", response_class=HTMLResponse)
async def pay_page(request: Request) -> HTMLResponse:
    params = _verified_request(dict(request.query_params))
    amount = int(params["vnp_Amount"]) // 100
    hidden = "".join(
        f'<input type="hidden" name="p_{html.escape(k)}" value="{html.escape(v)}">'
        for k, v in params.items()
    )
    buttons = "".join(
        f'<button name="outcome" value="{k}">{html.escape(label)}</button>'
        for k, label in OUTCOMES.items()
    )
    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cổng thanh toán giả lập</title>
<style>body{{font-family:system-ui;max-width:420px;margin:40px auto;padding:0 16px}}
button{{display:block;width:100%;margin:8px 0;padding:14px;font-size:16px;border-radius:10px;
border:1px solid #ccc;background:#fff;cursor:pointer}}.amt{{font-size:28px;font-weight:700}}</style>
</head><body><h2>🧪 Cổng thanh toán giả lập</h2>
<p>{html.escape(params.get("vnp_OrderInfo", ""))}</p>
<p class="amt">{amount:,}đ</p><p>Mã giao dịch: <code>{html.escape(params["vnp_TxnRef"])}</code></p>
<form method="post" action="/mock-gateway/pay/complete">{hidden}{buttons}</form>
</body></html>"""
    return HTMLResponse(page)


def _callback_params(request_params: dict[str, str], outcome: str) -> dict[str, str]:
    code = RESPONSE_CODES.get(outcome, "00")
    params = {
        "vnp_Amount": request_params["vnp_Amount"],
        "vnp_BankCode": "MOCK",
        "vnp_OrderInfo": request_params.get("vnp_OrderInfo", ""),
        "vnp_PayDate": vnp_time(utcnow()),
        "vnp_ResponseCode": code,
        "vnp_TmnCode": request_params["vnp_TmnCode"],
        "vnp_TransactionNo": str(secrets.randbelow(10**8)).zfill(8),
        "vnp_TransactionStatus": "00" if code == "00" else "02",
        "vnp_TxnRef": request_params["vnp_TxnRef"],
    }
    params["vnp_SecureHash"] = signing.sign(params, get_provider().secret)  # type: ignore[attr-defined]
    return params


async def deliver_ipn(params: dict[str, str]) -> str:
    """Giả lập cổng gọi IPN của shop: phiên DB riêng, như một request độc lập."""
    async with SessionLocal() as session:
        result = await handle_ipn(session, params, utcnow())
    log.info("Mock gateway IPN %s -> %s", params["vnp_TxnRef"], result.RspCode)
    return result.RspCode


@router.post("/pay/complete")
async def complete(request: Request, outcome: Annotated[Outcome, Form()]) -> RedirectResponse:
    form = await request.form()
    request_params = _verified_request(
        {k[2:]: str(v) for k, v in form.items() if k.startswith("p_")}
    )
    callback = _callback_params(request_params, outcome)

    if outcome == "success_late_ipn":
        from app.workers.tasks import deliver_mock_ipn  # import muộn: chỉ cần khi dùng Celery

        deliver_mock_ipn.apply_async(args=[callback], countdown=120)
    else:
        await deliver_ipn(callback)
        if outcome == "success_duplicate_ipn":
            await deliver_ipn(callback)  # cổng gửi lại IPN — shop phải idempotent

    query = signing.signed_query(
        {k: v for k, v in callback.items() if k != "vnp_SecureHash"},
        get_provider().secret,  # type: ignore[attr-defined]
    )
    return RedirectResponse(f"{request_params['vnp_ReturnUrl']}?{query}", status_code=303)

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
    "success": "Thanh toán thành công",
    "failed": "Thất bại (không đủ số dư)",
    "cancelled": "Khách hủy giao dịch",
    "success_late_ipn": "Thành công, IPN đến trễ 2 phút",
    "success_duplicate_ipn": "Thành công, IPN gửi 2 lần",
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
    order_info = html.escape(params.get("vnp_OrderInfo", ""))
    vnd = f"{amount:,}".replace(",", ".")
    txn = html.escape(params["vnp_TxnRef"])
    # Nút chính = thanh toán thành công; các kịch bản còn lại để demo xử lý lỗi / IPN của backend
    others = "".join(
        f'<button class="alt" name="outcome" value="{k}">{html.escape(label)}</button>'
        for k, label in OUTCOMES.items()
        if k != "success"
    )
    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cổng thanh toán giả lập</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;
font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
background:#eef1f5;color:#1f2937;display:flex;align-items:flex-start;
justify-content:center;padding:32px 16px}}
.card{{width:100%;max-width:420px;background:#fff;border-radius:20px;
box-shadow:0 10px 30px rgba(15,23,42,.08);overflow:hidden}}
.head{{background:#1e3a5f;color:#fff;padding:20px 24px}}
.badge{{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
background:rgba(255,255,255,.15);border-radius:999px;padding:4px 10px}}
.head h1{{font-size:18px;margin:10px 0 0}}
.body{{padding:24px}}
.label{{font-size:12px;color:#6b7280;margin:0}}
.amt{{font-size:34px;font-weight:800;margin:4px 0 16px;letter-spacing:-.02em}}
.row{{display:flex;justify-content:space-between;gap:12px;font-size:14px;padding:10px 0;
border-top:1px solid #f1f5f9}}
.row span:first-child{{color:#6b7280;white-space:nowrap}}
code{{font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:6px}}
button{{display:block;width:100%;font:inherit;cursor:pointer;border-radius:12px}}
.pay{{margin-top:20px;padding:15px;font-size:16px;font-weight:700;border:0;background:#1e3a5f;color:#fff}}
.pay:hover{{background:#16304f}}
details{{margin-top:16px;font-size:14px}}
summary{{cursor:pointer;color:#475569;padding:8px 0}}
.alt{{margin:8px 0 0;padding:12px;font-size:14px;border:1px solid #e2e8f0;
background:#fff;color:#334155;text-align:left}}
.alt:hover{{background:#f8fafc}}
.note{{font-size:12px;color:#94a3b8;text-align:center;margin:18px 0 0}}
</style></head><body>
<form class="card" method="post" action="/mock-gateway/pay/complete">{hidden}
<div class="head"><span class="badge">Sandbox</span>
<h1>Cổng thanh toán giả lập</h1></div>
<div class="body">
<p class="label">Số tiền thanh toán</p>
<p class="amt">{vnd}đ</p>
<div class="row"><span>Nội dung</span><span>{order_info}</span></div>
<div class="row"><span>Mã giao dịch</span><code>{txn}</code></div>
<button class="pay" name="outcome" value="success">Thanh toán {vnd}đ</button>
<details><summary>Kịch bản thử nghiệm khác</summary>{others}</details>
<p class="note">Môi trường demo: không có tiền thật được chuyển.</p>
</div></form>
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

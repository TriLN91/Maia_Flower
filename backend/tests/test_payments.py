import asyncio
from datetime import timedelta
from urllib.parse import parse_qsl, urlsplit

import pytest
from sqlalchemy import func, select, update

from app.api.mock_gateway import _callback_params
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import DeliverySlotDay, Order, OrderStatus, Payment, PaymentStatus
from app.services.inventory import utcnow
from app.services.order_workflow import expire_overdue_orders
from app.services.payments import signing
from app.services.payments.service import handle_ipn

# Dùng lại fixture dựng shop / đặt hàng của test checkout
from tests.test_checkout import (  # noqa: F401
    batch_available,
    ledger_sum,
    place_order,
    shop,
    slots,
    tomorrow,
)

SECRET = get_settings().mock_pay_secret


# ---------------------------------------------------------------- helpers
@pytest.fixture
async def paid_setup(shop, place_order):  # noqa: F811
    """Một lô 10 hồng, một đơn 'Đỏ Rực' × 1 (giữ 2 cành) đang chờ thanh toán."""
    batch = await shop["add_batch"]("rose", 10)
    r = await place_order([(shop["red"], 1)])
    assert r.status_code == 201, r.text
    return {"batch": batch, "order": r.json(), "shop": shop}


async def start_pay(client, token) -> dict[str, str]:
    r = await client.post(f"/api/v1/shop/orders/track/{token}/pay")
    assert r.status_code == 200, r.text
    return dict(parse_qsl(urlsplit(r.json()["payment_url"]).query))


async def ipn(params: dict[str, str]) -> str:
    async with SessionLocal() as s:
        return (await handle_ipn(s, params, utcnow())).RspCode


async def order_row(code: str) -> Order:
    async with SessionLocal() as s:
        return await s.scalar(select(Order).where(Order.code == code))


async def payments_of(code: str) -> list[Payment]:
    async with SessionLocal() as s:
        order_id = await s.scalar(select(Order.id).where(Order.code == code))
        return list((await s.scalars(select(Payment).where(Payment.order_id == order_id))).all())


async def expire_hold(code: str) -> None:
    async with SessionLocal() as s:
        await s.execute(
            update(Order)
            .where(Order.code == code)
            .values(hold_expires_at=utcnow() - timedelta(minutes=1))
        )
        await s.commit()


async def slot_reserved() -> int:
    async with SessionLocal() as s:
        return await s.scalar(select(func.coalesce(func.sum(DeliverySlotDay.reserved_count), 0)))


# ================================================================ Chữ ký
def test_signature_roundtrip_and_tamper_detection():
    params = {"vnp_Amount": "23000000", "vnp_TxnRef": "MF-1", "vnp_OrderInfo": "Đơn hoa"}
    signed = {**params, "vnp_SecureHash": signing.sign(params, SECRET)}
    assert signing.verify(signed, SECRET)
    assert signing.verify(dict(reversed(list(signed.items()))), SECRET)  # thứ tự không ảnh hưởng
    assert not signing.verify({**signed, "vnp_Amount": "100"}, SECRET)
    assert not signing.verify(signed, "another-secret-" + "x" * 30)
    assert not signing.verify(params, SECRET)  # thiếu chữ ký


def test_hash_data_follows_vnpay_rules():
    data = signing.hash_data(
        {"vnp_B": "a b", "vnp_A": "1", "vnp_Empty": "", "vnp_SecureHash": "x", "other": "y"}
    )
    assert data == "vnp_A=1&vnp_B=a+b"  # sắp xếp, bỏ rỗng / chữ ký / tham số ngoài vnp_


# ================================================================ Luồng đầy đủ qua cổng giả lập
async def test_full_payment_flow_through_mock_gateway(client, paid_setup):
    order = paid_setup["order"]
    r = await client.post(f"/api/v1/shop/orders/track/{order['tracking_token']}/pay")
    pay = r.json()
    assert pay["amount"] == order["total"]
    gateway = urlsplit(pay["payment_url"])

    page = await client.get(f"{gateway.path}?{gateway.query}")
    assert page.status_code == 200
    assert f"{order['total']:,}đ".replace(",", ".") in page.text  # định dạng số kiểu VN

    form = {f"p_{k}": v for k, v in parse_qsl(gateway.query)} | {"outcome": "success"}
    done = await client.post("/mock-gateway/pay/complete", data=form)
    assert done.status_code == 303
    back = urlsplit(done.headers["location"])
    assert back.path == "/api/v1/payments/mock/return"

    result = (await client.get(f"{back.path}?{back.query}")).json()
    assert result["order_status"] == "paid"
    assert result["payment_status"] == "succeeded"

    tracked = (await client.get(f"/api/v1/shop/orders/track/{order['tracking_token']}")).json()
    assert tracked["status"] == "paid"
    assert tracked["hold_expires_at"] is None
    assert [t["to_status"] for t in tracked["timeline"]] == ["pending_payment", "paid"]


async def test_gateway_rejects_tampered_payment_request(client, paid_setup):
    params = await start_pay(client, paid_setup["order"]["tracking_token"])
    params["vnp_Amount"] = "100"  # khách sửa số tiền trên URL
    r = await client.get("/mock-gateway/pay", params=params)
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_SIGNATURE"


# ================================================================ IPN
async def test_duplicate_ipn_is_idempotent(client, paid_setup):
    params = await start_pay(client, paid_setup["order"]["tracking_token"])
    callback = _callback_params(params, "success")

    assert await ipn(callback) == "00"
    assert await ipn(callback) == "02"  # đã xác nhận
    pays = await payments_of(paid_setup["order"]["code"])
    assert [p.status for p in pays] == [PaymentStatus.SUCCEEDED]
    assert (await order_row(paid_setup["order"]["code"])).status == OrderStatus.PAID
    assert await batch_available(paid_setup["batch"]) == 8  # không trừ kho lần nữa


async def test_ipn_rejects_bad_signature_amount_and_unknown_txn(client, paid_setup):
    params = await start_pay(client, paid_setup["order"]["tracking_token"])
    callback = _callback_params(params, "success")

    assert await ipn({**callback, "vnp_ResponseCode": "00", "vnp_Amount": "1"}) == "97"

    wrong_amount = {k: v for k, v in callback.items() if k != "vnp_SecureHash"}
    wrong_amount["vnp_Amount"] = "100"  # chữ ký hợp lệ nhưng số tiền không khớp giao dịch
    wrong_amount["vnp_SecureHash"] = signing.sign(wrong_amount, SECRET)
    assert await ipn(wrong_amount) == "04"

    unknown = {k: v for k, v in callback.items() if k != "vnp_SecureHash"}
    unknown["vnp_TxnRef"] = "NOPE"
    unknown["vnp_SecureHash"] = signing.sign(unknown, SECRET)
    assert await ipn(unknown) == "01"

    assert (await order_row(paid_setup["order"]["code"])).status == OrderStatus.PENDING_PAYMENT


async def test_ipn_endpoint_returns_vnpay_style_codes(client, paid_setup):
    params = await start_pay(client, paid_setup["order"]["tracking_token"])
    callback = _callback_params(params, "success")
    r = await client.get("/api/v1/payments/mock/ipn", params=callback)
    assert r.json() == {"RspCode": "00", "Message": "Confirm Success"}


async def test_failed_payment_can_be_retried(client, paid_setup):
    token = paid_setup["order"]["tracking_token"]
    first = await start_pay(client, token)
    assert await ipn(_callback_params(first, "failed")) == "00"
    assert (await order_row(paid_setup["order"]["code"])).status == OrderStatus.PENDING_PAYMENT

    second = await start_pay(client, token)
    assert second["vnp_TxnRef"] != first["vnp_TxnRef"]
    assert await ipn(_callback_params(second, "success")) == "00"

    pays = await payments_of(paid_setup["order"]["code"])
    assert [p.status for p in pays] == [PaymentStatus.FAILED, PaymentStatus.SUCCEEDED]
    assert pays[0].response_code == "51"


async def test_return_url_never_changes_order_state(client, paid_setup):
    """Return URL đi qua trình duyệt: chỉ để hiển thị, kể cả khi chữ ký hợp lệ."""
    params = await start_pay(client, paid_setup["order"]["tracking_token"])
    callback = _callback_params(params, "success")  # IPN chưa tới
    r = await client.get("/api/v1/payments/mock/return", params=callback)
    assert r.json()["gateway_success"] is True
    assert r.json()["order_status"] == "pending_payment"
    assert "đang xác nhận" in r.json()["message"]


async def test_cannot_pay_expired_or_already_paid_order(client, paid_setup):
    token = paid_setup["order"]["tracking_token"]
    params = await start_pay(client, token)
    await ipn(_callback_params(params, "success"))
    r = await client.post(f"/api/v1/shop/orders/track/{token}/pay")
    assert r.status_code == 409
    assert r.json()["code"] == "ORDER_NOT_PAYABLE"


async def test_cannot_start_payment_after_hold_expired(client, paid_setup):
    await expire_hold(paid_setup["order"]["code"])
    r = await client.post(f"/api/v1/shop/orders/track/{paid_setup['order']['tracking_token']}/pay")
    assert r.json()["code"] == "HOLD_EXPIRED"


# ================================================================ Nhả đơn quá hạn
async def test_expiry_job_releases_stock_and_slot(paid_setup):
    code, batch = paid_setup["order"]["code"], paid_setup["batch"]
    assert (await batch_available(batch), await slot_reserved()) == (8, 1)

    async with SessionLocal() as s:
        assert await expire_overdue_orders(s, utcnow()) == 0  # chưa tới hạn
    await expire_hold(code)
    async with SessionLocal() as s:
        assert await expire_overdue_orders(s, utcnow()) == 1

    assert (await order_row(code)).status == OrderStatus.EXPIRED
    assert await batch_available(batch) == await ledger_sum(batch) == 10
    assert await slot_reserved() == 0


async def test_celery_task_runs_expiry(paid_setup):
    from app.workers.tasks import expire_unpaid_orders

    await expire_hold(paid_setup["order"]["code"])
    # Task Celery là hàm đồng bộ tự tạo event loop -> chạy ở thread khác
    assert await asyncio.to_thread(expire_unpaid_orders.run) == 1


async def test_late_payment_re_reserves_stock_when_available(client, paid_setup):
    code, batch = paid_setup["order"]["code"], paid_setup["batch"]
    params = await start_pay(client, paid_setup["order"]["tracking_token"])
    await expire_hold(code)
    async with SessionLocal() as s:
        await expire_overdue_orders(s, utcnow())
    assert await batch_available(batch) == 10

    assert await ipn(_callback_params(params, "success")) == "00"  # tiền về trễ
    order = await order_row(code)
    assert order.status == OrderStatus.PAID
    assert await batch_available(batch) == await ledger_sum(batch) == 8
    assert await slot_reserved() == 1


async def test_late_payment_without_stock_needs_refund(client, paid_setup, place_order):  # noqa: F811
    code, shop_ = paid_setup["order"]["code"], paid_setup["shop"]
    params = await start_pay(client, paid_setup["order"]["tracking_token"])
    await expire_hold(code)
    async with SessionLocal() as s:
        await expire_overdue_orders(s, utcnow())
    # Trong lúc đó khách khác mua hết 10 cành
    assert (await place_order([(shop_["red"], 5)])).status_code == 201

    assert await ipn(_callback_params(params, "success")) == "00"
    assert (await order_row(code)).status == OrderStatus.NEEDS_REFUND
    [payment] = await payments_of(code)
    assert (payment.status, payment.needs_refund) == (PaymentStatus.SUCCEEDED, True)
    assert await batch_available(paid_setup["batch"]) == 0  # đơn của khách kia không bị ảnh hưởng


async def test_ipn_racing_expiry_job_stays_consistent(client, paid_setup):
    """IPN thành công và job nhả đơn chạy CÙNG LÚC trên một đơn vừa quá hạn: dù bên nào thắng,
    kết quả cuối là đơn PAID và kho chỉ bị trừ đúng 2 cành."""
    code, batch = paid_setup["order"]["code"], paid_setup["batch"]
    params = await start_pay(client, paid_setup["order"]["tracking_token"])
    await expire_hold(code)

    async def run_expiry():
        async with SessionLocal() as s:
            return await expire_overdue_orders(s, utcnow())

    await asyncio.gather(ipn(_callback_params(params, "success")), run_expiry())
    assert (await order_row(code)).status == OrderStatus.PAID
    assert await batch_available(batch) == await ledger_sum(batch) == 8
    assert await slot_reserved() == 1


# ================================================================ Quy trình đơn
@pytest.fixture
async def paid_order(client, paid_setup, owner_headers):
    params = await start_pay(client, paid_setup["order"]["tracking_token"])
    await ipn(_callback_params(params, "success"))
    order = await order_row(paid_setup["order"]["code"])
    return {**paid_setup, "id": order.id}


async def transition(client, headers, order_id, to_status):
    return await client.post(
        f"/api/v1/admin/orders/{order_id}/transition",
        json={"to_status": to_status},
        headers=headers,
    )


async def test_happy_path_workflow(client, paid_order, make_staff, login):
    await make_staff(email="tho@maiaflower.vn")
    staff = await login("tho@maiaflower.vn")
    for status in ("preparing", "delivering", "completed"):
        r = await transition(client, staff, paid_order["id"], status)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == status

    events = r.json()["events"]
    assert [e["to_status"] for e in events] == [
        "pending_payment",
        "paid",
        "preparing",
        "delivering",
        "completed",
    ]
    assert events[-1]["actor"] == "staff"


async def test_invalid_transition_lists_allowed_steps(client, paid_order, owner_headers):
    r = await transition(client, owner_headers, paid_order["id"], "completed")
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_TRANSITION"
    assert r.json()["extra"] == {"from": "paid", "allowed": ["needs_refund", "preparing"]}


async def test_owner_cancels_unpaid_order_releases_immediately(
    client, paid_setup, owner_headers, make_staff, login
):
    order_id = (await order_row(paid_setup["order"]["code"])).id
    await make_staff(email="tho@maiaflower.vn")
    staff = await login("tho@maiaflower.vn")
    assert (await transition(client, staff, order_id, "cancelled")).status_code == 403

    r = await transition(client, owner_headers, order_id, "cancelled")
    assert r.json()["status"] == "cancelled"
    assert await batch_available(paid_setup["batch"]) == 10
    assert await slot_reserved() == 0


async def test_cancel_paid_order_then_confirm_refund(client, paid_order, owner_headers):
    r = await transition(client, owner_headers, paid_order["id"], "needs_refund")
    assert r.json()["status"] == "needs_refund"
    assert r.json()["payments"][0]["needs_refund"] is True
    assert await batch_available(paid_order["batch"]) == 10

    r = await transition(client, owner_headers, paid_order["id"], "cancelled")
    assert r.json()["status"] == "cancelled"


async def test_admin_lists_orders_by_status_and_date(client, paid_order, owner_headers, tomorrow):  # noqa: F811
    r = await client.get(
        "/api/v1/admin/orders",
        params={"status": "paid", "delivery_date": str(tomorrow)},
        headers=owner_headers,
    )
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["item_count"] == 1
    other_day = await client.get(
        "/api/v1/admin/orders",
        params={"delivery_date": str(tomorrow + timedelta(days=1))},
        headers=owner_headers,
    )
    assert other_day.json()["total"] == 0

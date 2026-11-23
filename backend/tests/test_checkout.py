import asyncio
import re
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Batch, DeliverySlot, DeliverySlotDay, InventoryMovement, Order
from app.services.delivery_quote import issue_quote

ORDERS = "/api/v1/shop/orders"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
DELIVERY_KM = 2.0
DELIVERY_FEE = 20_000  # ≤ 3 km: phí cơ bản theo bảng phí mẫu


def vn_today():
    return datetime.now(VN).date()


@pytest.fixture
def tomorrow():
    return vn_today() + timedelta(days=1)


@pytest.fixture
async def slots():
    """Khung tối (sức chứa lớn) và khung sáng (chỉ 2 chỗ)."""
    async with SessionLocal() as s:
        evening = DeliverySlot(start_time=time(17), end_time=time(19), default_capacity=100)
        morning = DeliverySlot(start_time=time(8), end_time=time(10), default_capacity=2)
        s.add_all([evening, morning])
        await s.commit()
        return {"evening": evening.id, "morning": morning.id}


@pytest.fixture
async def shop(client, owner_headers):
    async def post(url, body):
        r = await client.post(url, json=body, headers=owner_headers)
        assert r.status_code == 201, r.text
        return r.json()

    rose = await post(
        "/api/v1/admin/flower-types",
        {"name": "Hồng đỏ", "color": "đỏ", "vase_life_days": 7, "reference_cost": 9000},
    )
    baby = await post(
        "/api/v1/admin/flower-types",
        {"name": "Baby", "color": "trắng", "vase_life_days": 10, "reference_cost": 3000},
    )
    supplier = await post("/api/v1/admin/suppliers", {"name": "Vườn Đà Lạt"})
    red = await post(
        "/api/v1/admin/templates",
        {
            "name": "Đỏ Rực",
            "price": 200_000,
            "items": [{"flower_type_id": rose["id"], "quantity": 2}],
        },
    )
    pastel = await post(
        "/api/v1/admin/templates",
        {
            "name": "Pastel",
            "price": 350_000,
            "items": [
                {"flower_type_id": rose["id"], "quantity": 3},
                {"flower_type_id": baby["id"], "quantity": 2},
            ],
        },
    )

    async def add_batch(flower: str, quantity: int, days_ago: float = 0) -> int:
        body = {
            "flower_type_id": rose["id"] if flower == "rose" else baby["id"],
            "supplier_id": supplier["id"],
            "quantity": quantity,
            "cost_per_stem": 8000,
        }
        if days_ago:
            body["received_at"] = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
        return (await post("/api/v1/admin/batches", body))["id"]

    return {
        "rose": rose["id"],
        "baby": baby["id"],
        "red": red["id"],
        "pastel": pastel["id"],
        "add_batch": add_batch,
    }


@pytest.fixture
def place_order(client, slots, tomorrow):
    async def _place(items, *, key=None, slot="evening", day=None, **overrides):
        body = {
            "items": [{"template_id": t, "quantity": q} for t, q in items],
            "customer_name": "Nguyễn Văn An",
            "customer_phone": "0909 123 456",
            "delivery_address": "12 Nguyễn Huệ, Quận 1, TP.HCM",
            "delivery_date": str(day or tomorrow),
            "slot_id": slots[slot],
            "delivery_quote_token": quote_token(),
            **overrides,
        }
        return await client.post(
            ORDERS, json=body, headers={"Idempotency-Key": key or str(uuid.uuid4())}
        )

    return _place


def quote_token(km: float = DELIVERY_KM, *, now: datetime | None = None) -> str:
    token, _ = issue_quote(
        lat=10.78, lng=106.70, distance_km=km, provider="test", now=now or datetime.now(UTC)
    )
    return token


async def batch_available(batch_id: int) -> int:
    async with SessionLocal() as s:
        return (await s.get(Batch, batch_id)).quantity_available


async def ledger_sum(batch_id: int) -> int:
    async with SessionLocal() as s:
        return await s.scalar(
            select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
                InventoryMovement.batch_id == batch_id
            )
        )


async def count_orders() -> int:
    async with SessionLocal() as s:
        return await s.scalar(select(func.count()).select_from(Order))


# ================================================================ Báo giá
async def test_cart_quote(client, shop):
    await shop["add_batch"]("rose", 10)
    await shop["add_batch"]("baby", 10)

    r = await client.post(
        "/api/v1/shop/cart/quote",
        json={
            "items": [
                {"template_id": shop["red"], "quantity": 2},
                {"template_id": shop["pastel"], "quantity": 1},
            ]
        },
    )
    assert r.status_code == 200
    q = r.json()
    assert q["subtotal"] == 2 * 200_000 + 350_000
    assert q["delivery_fee"] is None  # chưa có địa chỉ
    assert q["total"] == q["subtotal"]
    assert q["all_available"] is True  # 2×2 + 3 = 7 hồng ≤ 10


async def test_cart_quote_flags_shortage_across_lines(client, shop):
    await shop["add_batch"]("rose", 6)
    await shop["add_batch"]("baby", 10)
    # từng dòng riêng lẻ đều đủ, nhưng gộp lại cần 7 hồng > 6
    r = await client.post(
        "/api/v1/shop/cart/quote",
        json={
            "items": [
                {"template_id": shop["red"], "quantity": 2},
                {"template_id": shop["pastel"], "quantity": 1},
            ]
        },
    )
    q = r.json()
    assert q["all_available"] is False
    assert all(line["available"] is False for line in q["lines"])


# ================================================================ Tạo đơn
async def test_create_order_reserves_stock_and_slot(client, shop, place_order, owner_headers):
    batch = await shop["add_batch"]("rose", 10)

    r = await place_order([(shop["red"], 2)])
    assert r.status_code == 201, r.text
    o = r.json()
    assert re.fullmatch(r"MF-\d{6}-[A-HJ-NP-Z2-9]{4}", o["code"])
    assert len(o["tracking_token"]) >= 40
    assert o["status"] == "pending_payment"
    assert o["subtotal"] == 400_000
    assert o["delivery_fee"] == DELIVERY_FEE
    assert o["total"] == 400_000 + DELIVERY_FEE
    assert o["customer_phone_masked"] == "0909***456"
    hold = datetime.fromisoformat(o["hold_expires_at"]) - datetime.now(UTC)
    assert timedelta(minutes=14) < hold <= timedelta(minutes=15)

    assert await batch_available(batch) == await ledger_sum(batch) == 6

    # Admin thấy đơn lấy hoa từ lô nào
    async with SessionLocal() as s:
        order_id = await s.scalar(select(Order.id).where(Order.code == o["code"]))
    detail = (await client.get(f"/api/v1/admin/orders/{order_id}", headers=owner_headers)).json()
    allocations = detail["items"][0]["allocations"]
    assert allocations == [{"batch_id": batch, "flower_type_id": shop["rose"], "quantity": 4}]
    assert detail["customer_phone"] == "0909123456"

    # Khung giờ đã bị giữ 1 chỗ
    avail = await client.get(
        "/api/v1/shop/delivery-slots", params={"date": o["delivery_starts_at"][:10]}
    )
    evening = next(s for s in avail.json() if s["start_time"] == "17:00:00")
    assert evening["remaining"] == 99


async def test_fefo_takes_oldest_batch_first(client, shop, place_order, owner_headers):
    older = await shop["add_batch"]("rose", 3, days_ago=3)
    newer = await shop["add_batch"]("rose", 10)

    r = await place_order([(shop["red"], 2)])  # cần 4 hồng
    assert r.status_code == 201
    assert await batch_available(older) == 0
    assert await batch_available(newer) == 9


async def test_batch_expiring_before_delivery_is_skipped(shop, place_order):
    # Lô này hết hạn sau ~12 giờ — trước khung giao tối mai -> không được dùng
    await shop["add_batch"]("rose", 50, days_ago=6.5)
    r = await place_order([(shop["red"], 1)])
    assert r.status_code == 409
    assert r.json()["code"] == "OUT_OF_STOCK"


async def test_all_or_nothing_when_one_flower_is_missing(client, shop, place_order, tomorrow):
    rose = await shop["add_batch"]("rose", 20)  # có hồng, không có baby

    r = await place_order([(shop["red"], 1), (shop["pastel"], 1)])
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "OUT_OF_STOCK"
    assert body["extra"]["shortages"] == [
        {"flower_type_id": shop["baby"], "name": "Baby", "needed": 2, "available": 0}
    ]
    # Không có gì bị giữ: hồng nguyên vẹn, khung giờ nguyên vẹn, không có đơn
    assert await batch_available(rose) == 20
    assert await count_orders() == 0
    async with SessionLocal() as s:
        assert (
            await s.scalar(select(func.coalesce(func.sum(DeliverySlotDay.reserved_count), 0))) == 0
        )


async def test_demand_is_aggregated_across_cart_lines(shop, place_order):
    await shop["add_batch"]("rose", 6)
    await shop["add_batch"]("baby", 10)
    r = await place_order([(shop["red"], 2), (shop["pastel"], 1)])  # 4 + 3 = 7 hồng
    assert r.status_code == 409
    assert r.json()["extra"]["shortages"][0]["needed"] == 7


async def test_inactive_template_cannot_be_ordered(client, shop, place_order, owner_headers):
    await shop["add_batch"]("rose", 10)
    await client.patch(
        f"/api/v1/admin/templates/{shop['red']}", json={"is_active": False}, headers=owner_headers
    )
    r = await place_order([(shop["red"], 1)])
    assert r.status_code == 400
    assert r.json()["code"] == "TEMPLATE_UNAVAILABLE"


# ================================================================ Idempotency
async def test_same_idempotency_key_returns_same_order(shop, place_order):
    batch = await shop["add_batch"]("rose", 10)
    first = await place_order([(shop["red"], 1)], key="order-key-123")
    second = await place_order([(shop["red"], 1)], key="order-key-123")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert first.json()["code"] == second.json()["code"]
    assert await count_orders() == 1
    assert await batch_available(batch) == 8  # chỉ trừ một lần


async def test_same_key_with_different_body_is_rejected(shop, place_order):
    await shop["add_batch"]("rose", 10)
    await place_order([(shop["red"], 1)], key="order-key-456")
    r = await place_order([(shop["red"], 2)], key="order-key-456")
    assert r.status_code == 422
    assert r.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_concurrent_requests_with_same_key_create_one_order(shop, place_order):
    batch = await shop["add_batch"]("rose", 20)
    responses = await asyncio.gather(
        *[place_order([(shop["red"], 1)], key="double-click-key") for _ in range(5)]
    )
    assert {r.status_code for r in responses} <= {200, 201}
    assert len({r.json()["code"] for r in responses}) == 1
    assert await count_orders() == 1
    assert await batch_available(batch) == 18


async def test_idempotency_key_header_is_required(client, shop, slots, tomorrow):
    r = await client.post(ORDERS, json={"items": []})
    assert r.status_code == 422


# ================================================================ Khung giờ
async def test_slot_capacity_is_enforced(shop, place_order):
    await shop["add_batch"]("rose", 50)
    for _ in range(2):
        assert (await place_order([(shop["red"], 1)], slot="morning")).status_code == 201
    r = await place_order([(shop["red"], 1)], slot="morning")
    assert r.status_code == 409
    assert r.json()["code"] == "SLOT_FULL"


@pytest.mark.parametrize("days", [-1, 30])
async def test_slot_outside_booking_window(shop, place_order, days):
    await shop["add_batch"]("rose", 10)
    r = await place_order([(shop["red"], 1)], day=vn_today() + timedelta(days=days))
    assert r.status_code == 400
    assert r.json()["code"] == "SLOT_OUT_OF_WINDOW"


async def test_slot_availability_listing(client, slots, tomorrow):
    r = await client.get("/api/v1/shop/delivery-slots", params={"date": str(tomorrow)})
    rows = r.json()
    assert [(s["start_time"], s["remaining"], s["bookable"]) for s in rows] == [
        ("08:00:00", 2, True),
        ("17:00:00", 100, True),
    ]
    past = await client.get(
        "/api/v1/shop/delivery-slots", params={"date": str(vn_today() - timedelta(days=1))}
    )
    assert {s["reason"] for s in past.json()} == {"OUT_OF_WINDOW"}


# ================================================================ Dữ liệu khách
async def test_phone_is_normalized_and_validated(shop, place_order):
    await shop["add_batch"]("rose", 10)
    ok = await place_order([(shop["red"], 1)], customer_phone="+84 909-123-456")
    assert ok.status_code == 201
    assert ok.json()["customer_phone_masked"] == "0909***456"

    bad = await place_order([(shop["red"], 1)], customer_phone="12345")
    assert bad.status_code == 422


async def test_track_order_by_token(client, shop, place_order):
    await shop["add_batch"]("rose", 10)
    created = (await place_order([(shop["red"], 1)])).json()

    r = await client.get(f"{ORDERS}/track/{created['tracking_token']}")
    assert r.status_code == 200
    tracked = r.json()
    assert tracked["code"] == created["code"]
    assert "tracking_token" not in tracked
    assert "allocations" not in tracked["items"][0]
    assert "customer_phone" not in tracked

    assert (await client.get(f"{ORDERS}/track/not-a-real-token")).status_code == 404


# ================================================================ Đồng thời ⭐
async def test_50_concurrent_orders_never_oversell(shop, place_order):
    """20 cành hồng, mỗi bó cần 2 cành, 50 khách bấm đặt cùng lúc:
    đúng 10 đơn thành công, 40 đơn nhận OUT_OF_STOCK, kho về 0, sổ kho khớp."""
    batch = await shop["add_batch"]("rose", 20)

    responses = await asyncio.gather(*[place_order([(shop["red"], 1)]) for _ in range(50)])

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201] * 10 + [409] * 40
    assert {r.json()["code"] for r in responses if r.status_code == 409} == {"OUT_OF_STOCK"}
    assert await batch_available(batch) == await ledger_sum(batch) == 0
    assert await count_orders() == 10


async def test_concurrent_orders_respect_slot_capacity(shop, place_order):
    """Khung sáng chỉ 2 chỗ, hoa dư thừa, 10 khách cùng đặt: đúng 2 đơn thành công."""
    await shop["add_batch"]("rose", 100)

    responses = await asyncio.gather(
        *[place_order([(shop["red"], 1)], slot="morning") for _ in range(10)]
    )
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201] * 2 + [409] * 8
    async with SessionLocal() as s:
        assert await s.scalar(select(func.sum(DeliverySlotDay.reserved_count))) == 2


# ================================================================ Phí ship trong đơn
async def test_cart_quote_with_delivery_token(client, shop):
    await shop["add_batch"]("rose", 10)
    r = await client.post(
        "/api/v1/shop/cart/quote",
        json={
            "items": [{"template_id": shop["red"], "quantity": 1}],
            "delivery_quote_token": quote_token(7.4),
        },
    )
    assert r.json()["delivery_fee"] == 42_000
    assert r.json()["total"] == 200_000 + 42_000


async def test_order_stores_distance_and_fee(client, shop, place_order, owner_headers):
    await shop["add_batch"]("rose", 10)
    r = await place_order([(shop["red"], 1)], delivery_quote_token=quote_token(12.0))
    assert r.status_code == 201
    assert r.json()["delivery_fee"] == 69_000

    async with SessionLocal() as s:
        order = await s.scalar(select(Order).where(Order.code == r.json()["code"]))
    assert (order.delivery_distance_km, order.delivery_lat, order.delivery_lng) == (
        12.0,
        10.78,
        106.70,
    )


async def test_free_shipping_applies_to_order(shop, place_order):
    await shop["add_batch"]("rose", 100)
    r = await place_order([(shop["red"], 8)], delivery_quote_token=quote_token(4.0))  # 1,6 triệu
    assert r.json()["delivery_fee"] == 0


@pytest.mark.parametrize(
    ("token_factory", "code"),
    [
        (lambda: quote_token() + "x", "INVALID_DELIVERY_QUOTE"),
        (lambda: quote_token(now=datetime.now(UTC) - timedelta(hours=1)), "DELIVERY_QUOTE_EXPIRED"),
        (lambda: "not-a-token", "INVALID_DELIVERY_QUOTE"),
        (lambda: quote_token(20.0), "OUT_OF_DELIVERY_RANGE"),
    ],
    ids=["tampered", "expired", "garbage", "out-of-range"],
)
async def test_bad_delivery_quote_rejects_order_without_holding_anything(
    shop, place_order, token_factory, code
):
    batch = await shop["add_batch"]("rose", 10)
    r = await place_order([(shop["red"], 1)], delivery_quote_token=token_factory())
    assert r.status_code == 400
    assert r.json()["code"] == code
    assert await batch_available(batch) == 10
    assert await count_orders() == 0

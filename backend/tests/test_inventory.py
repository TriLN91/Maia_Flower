import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Batch, InventoryMovement

B = "/api/v1/admin/batches"


@pytest.fixture
async def staff_headers(make_staff, login):
    await make_staff(email="tho@maiaflower.vn")
    return await login("tho@maiaflower.vn")


@pytest.fixture
async def setup(client, owner_headers):
    """Một loại hoa hồng (tươi 7 ngày), một baby (10 ngày), một nhà cung cấp."""

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
    return {"rose": rose["id"], "baby": baby["id"], "supplier": supplier["id"]}


@pytest.fixture
def import_batch(client, owner_headers, setup):
    async def _import(
        quantity=20, *, flower="rose", days_ago=0.0, cost=8000, headers=None, **extra
    ) -> dict:
        body = {
            "flower_type_id": setup[flower],
            "supplier_id": setup["supplier"],
            "quantity": quantity,
            "cost_per_stem": cost,
            **extra,
        }
        if days_ago:
            body["received_at"] = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
        r = await client.post(B, json=body, headers=headers or owner_headers)
        assert r.status_code == 201, r.text
        return r.json()

    return _import


async def ledger_sum(batch_id: int) -> int:
    async with SessionLocal() as s:
        return await s.scalar(
            select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
                InventoryMovement.batch_id == batch_id
            )
        )


async def available(batch_id: int) -> int:
    async with SessionLocal() as s:
        return (await s.get(Batch, batch_id)).quantity_available


# ---------------------------------------------------------------- Nhập lô
async def test_import_batch_defaults_and_ledger(client, staff_headers, import_batch):
    batch = await import_batch(20, headers=staff_headers)  # thợ bó được nhập lô

    assert batch["quantity_received"] == batch["quantity_available"] == 20
    assert batch["status"] == "active"
    assert batch["freshness"] == pytest.approx(1.0, abs=0.01)
    assert batch["days_left"] == pytest.approx(7.0, abs=0.01)  # = số ngày tươi của hồng
    assert batch["is_sellable"] is True

    r = await client.get(f"{B}/{batch['id']}/movements", headers=staff_headers)
    assert [(m["type"], m["quantity"]) for m in r.json()] == [("import", 20)]


async def test_backdated_batch_has_lower_freshness(import_batch):
    batch = await import_batch(10, days_ago=3.5)  # 3,5 / 7 ngày
    assert batch["freshness"] == pytest.approx(0.5, abs=0.01)
    assert batch["days_left"] == pytest.approx(3.5, abs=0.01)


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"received_at": "2099-01-01T00:00:00Z"}, "INVALID_RECEIVED_AT"),
        ({"received_at": "2020-01-01T00:00:00Z"}, "INVALID_RECEIVED_AT"),
        ({"expected_expiry_at": "2020-01-01T00:00:00Z"}, "INVALID_EXPIRY"),
    ],
)
async def test_import_validation(client, owner_headers, setup, override, code):
    body = {
        "flower_type_id": setup["rose"],
        "supplier_id": setup["supplier"],
        "quantity": 10,
        "cost_per_stem": 8000,
        **override,
    }
    r = await client.post(B, json=body, headers=owner_headers)
    assert r.status_code == 400
    assert r.json()["code"] == code


async def test_naive_datetime_is_rejected(client, owner_headers, setup):
    body = {
        "flower_type_id": setup["rose"],
        "supplier_id": setup["supplier"],
        "quantity": 10,
        "cost_per_stem": 8000,
        "received_at": "2026-11-20T08:00:00",  # thiếu múi giờ -> mơ hồ
    }
    assert (await client.post(B, json=body, headers=owner_headers)).status_code == 422


async def test_cannot_import_from_inactive_supplier(client, owner_headers, setup, import_batch):
    await client.patch(
        f"/api/v1/admin/suppliers/{setup['supplier']}",
        json={"is_active": False},
        headers=owner_headers,
    )
    r = await client.post(
        B,
        json={
            "flower_type_id": setup["rose"],
            "supplier_id": setup["supplier"],
            "quantity": 1,
            "cost_per_stem": 1,
        },
        headers=owner_headers,
    )
    assert r.status_code == 400
    assert r.json()["code"] == "INACTIVE_SUPPLIER"


# ---------------------------------------------------------------- Hao hụt / kiểm kê
async def test_record_waste_until_depleted(client, staff_headers, import_batch):
    batch = await import_batch(10)
    url = f"{B}/{batch['id']}/waste"

    r = await client.post(url, json={"quantity": 4, "reason": "Gãy cành"}, headers=staff_headers)
    assert r.json()["quantity_available"] == 6

    r = await client.post(url, json={"quantity": 7, "reason": "Héo"}, headers=staff_headers)
    assert r.status_code == 400
    assert r.json()["code"] == "INSUFFICIENT_STOCK"
    assert r.json()["extra"]["available"] == 6

    r = await client.post(url, json={"quantity": 6, "reason": "Héo"}, headers=staff_headers)
    assert r.json()["quantity_available"] == 0
    assert r.json()["status"] == "depleted"
    assert r.json()["is_sellable"] is False


async def test_adjust_to_counted_quantity(client, owner_headers, staff_headers, import_batch):
    batch = await import_batch(20)
    url = f"{B}/{batch['id']}/adjust"

    denied = await client.post(
        url, json={"counted_quantity": 18, "reason": "x"}, headers=staff_headers
    )
    assert denied.status_code == 403

    r = await client.post(
        url, json={"counted_quantity": 18, "reason": "Kiểm kê cuối ngày"}, headers=owner_headers
    )
    assert r.json()["quantity_available"] == 18

    same = await client.post(
        url, json={"counted_quantity": 18, "reason": "Đếm lại"}, headers=owner_headers
    )
    assert same.json()["code"] == "NO_CHANGE"

    moves = (await client.get(f"{B}/{batch['id']}/movements", headers=owner_headers)).json()
    assert [(m["type"], m["quantity"]) for m in moves] == [("import", 20), ("adjust", -2)]


async def test_discard_closes_batch(client, owner_headers, import_batch):
    batch = await import_batch(15, days_ago=8)  # đã quá hạn (hồng 7 ngày)
    assert batch["is_sellable"] is False

    r = await client.post(
        f"{B}/{batch['id']}/discard", json={"reason": "Quá hạn"}, headers=owner_headers
    )
    assert r.json()["status"] == "discarded"
    assert r.json()["quantity_available"] == 0

    r = await client.post(
        f"{B}/{batch['id']}/waste", json={"quantity": 1, "reason": "x"}, headers=owner_headers
    )
    assert r.json()["code"] == "BATCH_CLOSED"


async def test_ledger_always_matches_stock(client, owner_headers, import_batch):
    """Bất biến cốt lõi: tồn kho = tổng sổ kho, sau mọi thao tác."""
    batch = await import_batch(50)
    bid = batch["id"]
    await client.post(
        f"{B}/{bid}/waste", json={"quantity": 7, "reason": "a"}, headers=owner_headers
    )
    await client.post(
        f"{B}/{bid}/adjust", json={"counted_quantity": 45, "reason": "b"}, headers=owner_headers
    )
    await client.post(
        f"{B}/{bid}/waste", json={"quantity": 5, "reason": "c"}, headers=owner_headers
    )
    await client.post(
        f"{B}/{bid}/waste", json={"quantity": 99, "reason": "d"}, headers=owner_headers
    )

    assert await available(bid) == await ledger_sum(bid) == 40


async def test_concurrent_waste_never_oversells(client, owner_headers, import_batch):
    """10 yêu cầu ghi hỏng 3 cành chạy đồng thời trên lô 20 cành:
    nhờ khóa dòng, đúng 6 yêu cầu thành công, tồn còn 2, không bao giờ âm."""
    batch = await import_batch(20)
    url = f"{B}/{batch['id']}/waste"

    responses = await asyncio.gather(
        *[
            client.post(url, json={"quantity": 3, "reason": f"#{i}"}, headers=owner_headers)
            for i in range(10)
        ]
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [200] * 6 + [400] * 4
    assert await available(batch["id"]) == await ledger_sum(batch["id"]) == 2


# ---------------------------------------------------------------- Sửa lô / độ tươi
async def test_staff_can_lower_freshness_but_not_change_expiry(
    client, staff_headers, owner_headers, import_batch
):
    batch = await import_batch(10)
    url = f"{B}/{batch['id']}"

    r = await client.patch(url, json={"freshness_override": 0.4}, headers=staff_headers)
    assert r.status_code == 200
    assert r.json()["freshness"] == pytest.approx(0.4)

    r = await client.patch(
        url, json={"expected_expiry_at": "2099-01-01T00:00:00Z"}, headers=staff_headers
    )
    assert r.status_code == 403
    assert r.json()["extra"]["fields"] == ["expected_expiry_at"]

    new_expiry = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    r = await client.patch(url, json={"expected_expiry_at": new_expiry}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["days_left"] == pytest.approx(2.0, abs=0.01)


async def test_list_batches_in_fefo_order(client, staff_headers, import_batch):
    newer = await import_batch(5, days_ago=1)
    older = await import_batch(5, days_ago=4)
    await import_batch(5, flower="baby")

    r = await client.get(
        B, params={"flower_type_id": newer["flower_type"]["id"]}, headers=staff_headers
    )
    assert [b["id"] for b in r.json()] == [older["id"], newer["id"]]


# ---------------------------------------------------------------- Tổng hợp tồn kho
async def test_inventory_summary(client, staff_headers, import_batch):
    await import_batch(10, days_ago=6)  # còn ~1 ngày -> sắp hết hạn
    await import_batch(30, days_ago=0)  # tươi
    await import_batch(8, days_ago=9)  # đã quá hạn -> không bán được

    rows = {
        r["flower_type"]["name"]: r
        for r in (await client.get("/api/v1/admin/inventory", headers=staff_headers)).json()
    }
    rose = rows["Hồng đỏ"]
    assert rose["total_available"] == 48
    assert rose["sellable"] == 40
    assert rose["expiring_soon"] == 10
    assert rose["batch_count"] == 3
    # TB theo số cành: (10 × 1/7 + 30 × 1.0) / 40
    assert rose["avg_freshness"] == pytest.approx((10 * (1 / 7) + 30) / 40, abs=0.01)

    assert rows["Baby"]["total_available"] == 0
    assert rows["Baby"]["avg_freshness"] is None


# ---------------------------------------------------------------- Giá vốn mẫu
@pytest.mark.parametrize(
    ("price", "warnings"),
    [
        (100_000, []),
        (80_000, ["LOW_MARGIN_AT_MAX_DISCOUNT"]),
        (50_000, ["BELOW_COST", "LOW_MARGIN_AT_MAX_DISCOUNT"]),
    ],
)
async def test_template_cost_and_margin_warnings(
    client, owner_headers, setup, import_batch, price, warnings
):
    await import_batch(10, cost=8_000)
    await import_batch(30, cost=10_000)
    # hồng: (10×8000 + 30×10000) / 40 = 9500 ; baby chưa có lô -> giá tham khảo 3000
    r = await client.post(
        "/api/v1/admin/templates",
        json={
            "name": "Mix",
            "price": price,
            "items": [
                {"flower_type_id": setup["rose"], "quantity": 5},
                {"flower_type_id": setup["baby"], "quantity": 3},
            ],
        },
        headers=owner_headers,
    )
    tpl_id = r.json()["id"]

    cost = (
        await client.get(f"/api/v1/admin/templates/{tpl_id}/cost", headers=owner_headers)
    ).json()
    lines = {line["flower_type"]["name"]: line for line in cost["lines"]}
    assert (lines["Hồng đỏ"]["unit_cost"], lines["Hồng đỏ"]["cost_source"]) == (9500, "batches")
    assert (lines["Baby"]["unit_cost"], lines["Baby"]["cost_source"]) == (3000, "reference")
    assert cost["cost"] == 5 * 9500 + 3 * 3000 == 56_500
    assert cost["price_floor"] == 67_800  # 56 500 × 1,2
    assert cost["lowest_price_after_discount"] == price * 70 // 100
    assert cost["warnings"] == warnings


async def test_cost_endpoint_is_owner_only(client, staff_headers):
    assert (
        await client.get("/api/v1/admin/templates/1/cost", headers=staff_headers)
    ).status_code == 403

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Order
from app.schemas.settings import PricingSettings
from app.services.inventory import utcnow
from app.services.pricing import decide_discount, max_pct_for_margin, recompute
from tests.test_checkout import place_order, quote_token, slots, tomorrow  # noqa: F401

S = PricingSettings()  # bậc: ≤2 ngày 10%, ≤1 ngày 20%; trần 30%; biên 20%; bước ±10


def decide(**kw):
    base = dict(
        recipe={1: 5, 2: 7},
        flower_pct={1: 20},
        price=500_000,
        cost=100_000,
        current_pct=0,
        settings=S,
    )
    return decide_discount(**{**base, **kw})


# ================================================================ Hàm thuần
def test_weighted_by_stems_in_recipe():
    # 5 trong 12 cành đang giảm 20% -> 8,33% -> làm tròn 8%
    d = decide()
    assert (d.raw_pct, d.target_pct, d.new_pct, d.limits) == (8.33, 8, 8, [])


def test_tier_picks_strictest_matching():
    assert S.flower_discount(1.8) == 10
    assert S.flower_discount(0.5) == 20
    assert S.flower_discount(2.5) == 0


def test_max_discount_cap():
    d = decide(recipe={1: 10}, flower_pct={1: 50}, current_pct=30)
    assert (d.target_pct, d.new_pct) == (30, 30)
    assert "max_discount" in d.limits


def test_margin_floor():
    # vốn 400k, biên 20% -> giá sau giảm ≥ 480k -> giảm tối đa 4%
    assert max_pct_for_margin(500_000, 400_000, 20) == 4
    d = decide(recipe={1: 10}, cost=400_000)
    assert (d.target_pct, d.margin_cap_pct) == (4, 4)
    assert "margin_floor" in d.limits
    # đã lỗ sẵn -> không giảm
    assert max_pct_for_margin(500_000, 600_000, 20) == 0


def test_step_limit_both_directions():
    up = decide(recipe={1: 10}, current_pct=0)  # mục tiêu 20
    assert (up.target_pct, up.new_pct, up.limits) == (20, 10, ["step"])
    down = decide(recipe={1: 10}, flower_pct={}, current_pct=25)  # hết dư thừa
    assert (down.target_pct, down.new_pct, down.limits) == (0, 15, ["step"])


def test_kill_switch_and_lock_reset_immediately():
    off = decide(current_pct=25, settings=S.model_copy(update={"enabled": False}))
    assert (off.new_pct, off.limits) == (0, ["disabled"])
    locked = decide(current_pct=25, locked=True)
    assert (locked.new_pct, locked.limits) == (0, ["locked"])


def test_settings_validation():
    with pytest.raises(ValueError, match="within horizon_days"):
        PricingSettings(horizon_days=1, tiers=[{"days_left_max": 2, "pct": 10}])


# ================================================================ Tích hợp
@pytest.fixture
async def setup(client, owner_headers):
    async def post(url, body):
        r = await client.post(url, json=body, headers=owner_headers)
        assert r.status_code == 201, r.text
        return r.json()

    rose = await post(
        "/api/v1/admin/flower-types",
        {"name": "Hồng", "color": "đỏ", "vase_life_days": 7, "reference_cost": 8000},
    )
    leaf = await post(
        "/api/v1/admin/flower-types",
        {"name": "Lá", "color": "xanh", "vase_life_days": 14, "reference_cost": 1000},
    )
    sup = await post("/api/v1/admin/suppliers", {"name": "NCC"})
    mixed = await post(
        "/api/v1/admin/templates",
        {
            "name": "Mix",
            "price": 300_000,
            "items": [
                {"flower_type_id": rose["id"], "quantity": 5},
                {"flower_type_id": leaf["id"], "quantity": 7},
            ],
        },
    )
    all_rose = await post(
        "/api/v1/admin/templates",
        {
            "name": "Toàn Hồng",
            "price": 400_000,
            "items": [{"flower_type_id": rose["id"], "quantity": 10}],
        },
    )
    premium = await post(
        "/api/v1/admin/templates",
        {
            "name": "Cao Cấp",
            "price": 900_000,
            "discount_locked": True,
            "items": [{"flower_type_id": rose["id"], "quantity": 20}],
        },
    )

    async def add_batch(flower, qty, days_ago=0.0):
        body = {
            "flower_type_id": flower,
            "supplier_id": sup["id"],
            "quantity": qty,
            "cost_per_stem": 8000,
        }
        if days_ago:
            body["received_at"] = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
        return (await post("/api/v1/admin/batches", body))["id"]

    await add_batch(leaf["id"], 200)
    return {
        "rose": rose["id"],
        "leaf": leaf["id"],
        "mixed": mixed["id"],
        "all_rose": all_rose["id"],
        "premium": premium["id"],
        "add_batch": add_batch,
    }


async def run_recompute(client, owner_headers):
    r = await client.post("/api/v1/admin/pricing/recompute", headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()


async def shop_prices(client) -> dict[str, tuple[int, int]]:
    items = (await client.get("/api/v1/shop/templates")).json()["items"]
    return {t["name"]: (t["discount_pct"], t["final_price"]) for t in items}


async def test_surplus_flowers_get_discounted(client, owner_headers, setup):
    await setup["add_batch"](setup["rose"], 50, days_ago=6.3)  # còn ~0,7 ngày -> bậc 20%
    result = await run_recompute(client, owner_headers)
    assert result["flowers_in_surplus"] == 1

    prices = await shop_prices(client)
    assert prices["Mix"] == (8, 276_000)  # 5/12 cành × 20% ≈ 8%
    assert prices["Toàn Hồng"] == (10, 360_000)  # mục tiêu 20%, bước ±10 -> 10% lần đầu
    assert prices["Cao Cấp"] == (0, 900_000)  # mẫu khóa giảm giá

    await run_recompute(client, owner_headers)
    assert (await shop_prices(client))["Toàn Hồng"] == (20, 320_000)  # lần sau mới tới 20%

    urgency = (await client.get("/api/v1/admin/urgency", headers=owner_headers)).json()
    rose = next(u for u in urgency if u["name"] == "Hồng")
    assert (rose["expiring_qty"], rose["surplus"], rose["discount_pct"]) == (50, 50, 20)


async def test_no_discount_when_demand_will_absorb_stock(client, owner_headers, setup, place_order):  # noqa: F811
    """Hoa sắp hết hạn nhưng lịch sử cho thấy đằng nào cũng bán hết -> không giảm."""
    await setup["add_batch"](setup["rose"], 400)  # lô tươi để bán
    for _ in range(10):  # 14 ngày qua bán 10 × 10 = 100 cành hồng (~7/ngày -> 14 cành/2 ngày)
        assert (await place_order([(setup["all_rose"], 1)])).status_code == 201
    await setup["add_batch"](setup["rose"], 12, days_ago=6.3)  # 12 cành sắp hết hạn < 14 dự kiến

    await run_recompute(client, owner_headers)
    urgency = (await client.get("/api/v1/admin/urgency", headers=owner_headers)).json()
    rose = next(u for u in urgency if u["name"] == "Hồng")
    assert rose["expiring_qty"] == 12
    assert rose["expected_demand"] == pytest.approx(100 / 14 * 2, abs=0.01)
    assert (rose["surplus"], rose["discount_pct"]) == (0, 0)
    assert (await shop_prices(client))["Toàn Hồng"] == (0, 400_000)


async def test_order_snapshots_discount_at_order_time(
    client,
    owner_headers,
    setup,
    place_order,  # noqa: F811
):
    await setup["add_batch"](setup["rose"], 50, days_ago=6.3)
    await setup["add_batch"](setup["rose"], 50)
    await run_recompute(client, owner_headers)

    r = await place_order([(setup["all_rose"], 1)], delivery_quote_token=quote_token(2.0))
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["items"][0]["discount_pct"] == 10
    assert o["items"][0]["line_total"] == 360_000
    assert o["discount_total"] == 40_000
    assert o["total"] == 360_000 + 20_000

    # Tắt công tắc tổng: giá shop về gốc ngay, đơn cũ giữ nguyên giá đã chốt
    settings = (await client.get("/api/v1/admin/settings/pricing", headers=owner_headers)).json()
    settings["enabled"] = False
    r = await client.put("/api/v1/admin/settings/pricing", json=settings, headers=owner_headers)
    assert r.status_code == 200
    assert (await shop_prices(client))["Toàn Hồng"] == (0, 400_000)
    async with SessionLocal() as s:
        order = await s.scalar(select(Order).where(Order.code == o["code"]))
    assert order.discount_total == 40_000


async def test_discount_log_explains_why(client, owner_headers, setup):
    await setup["add_batch"](setup["rose"], 50, days_ago=6.3)
    await run_recompute(client, owner_headers)
    log = (
        await client.get(
            f"/api/v1/admin/templates/{setup['all_rose']}/discount-log", headers=owner_headers
        )
    ).json()
    assert len(log) == 1
    entry = log[0]
    assert (entry["old_pct"], entry["new_pct"]) == (0, 10)
    assert entry["reason"]["target_pct"] == 20
    assert entry["reason"]["limits"] == ["step"]
    assert entry["reason"]["flowers"][0]["name"] == "Hồng"
    assert entry["reason"]["flowers"][0]["surplus"] == 50


async def test_discount_is_removed_when_surplus_is_gone(client, owner_headers, setup):
    batch = await setup["add_batch"](setup["rose"], 50, days_ago=6.3)
    await run_recompute(client, owner_headers)
    await client.post(
        f"/api/v1/admin/batches/{batch}/discard", json={"reason": "Héo"}, headers=owner_headers
    )
    await run_recompute(client, owner_headers)
    prices = await shop_prices(client)
    assert prices["Toàn Hồng"] == (0, 400_000)
    assert prices["Mix"] == (0, 300_000)


async def test_fresh_today_lists_discounted_first(client, owner_headers, setup):
    await setup["add_batch"](setup["rose"], 50, days_ago=6.3)
    await run_recompute(client, owner_headers)
    fresh = (await client.get("/api/v1/shop/templates/fresh-today")).json()
    assert [t["name"] for t in fresh] == ["Toàn Hồng", "Mix", "Cao Cấp"]
    assert fresh[0]["discount_pct"] == 10
    detail = (await client.get("/api/v1/shop/templates/toan-hong")).json()
    assert detail["final_price"] == 360_000


async def test_pricing_admin_permissions(client, setup, make_staff, login):
    await make_staff(email="tho@maiaflower.vn")
    staff = await login("tho@maiaflower.vn")
    assert (await client.get("/api/v1/admin/urgency", headers=staff)).status_code == 200
    assert (await client.post("/api/v1/admin/pricing/recompute", headers=staff)).status_code == 403
    assert (await client.get("/api/v1/admin/settings/pricing", headers=staff)).status_code == 403


async def test_concurrent_recomputes_are_serialized(setup):
    """Hai lần tính chạy cùng lúc (job + bấm tay): khóa tư vấn bắt chạy lần lượt, nên bước
    giới hạn vẫn đúng: 0 -> 10 -> 20, không phải cả hai cùng thấy 0 rồi cùng ghi 10."""
    import asyncio

    await setup["add_batch"](setup["rose"], 50, days_ago=6.3)

    async def run():
        async with SessionLocal() as s:
            return await recompute(s, utcnow())

    await asyncio.gather(run(), run())
    async with SessionLocal() as s:
        from app.services.pricing import current_discounts

        assert (await current_discounts(s, [setup["all_rose"]]))[setup["all_rose"]] == 20


async def test_admin_template_list_shows_current_discount(client, owner_headers, setup):
    await setup["add_batch"](setup["rose"], 50, days_ago=6.3)
    await run_recompute(client, owner_headers)
    rows = (await client.get("/api/v1/admin/templates", headers=owner_headers)).json()
    by_name = {t["name"]: t["current_discount_pct"] for t in rows}
    assert by_name == {"Mix": 8, "Toàn Hồng": 10, "Cao Cấp": 0}


async def test_tiny_surplus_does_not_trigger_discount(client, owner_headers, setup):
    """Phát hiện khi xem trang quản trị: dư 1 cành từng kéo cả bó giảm 9%."""
    await setup["add_batch"](setup["rose"], 4, days_ago=6.3)  # dư 4 cành < ngưỡng 5
    await run_recompute(client, owner_headers)
    urgency = (await client.get("/api/v1/admin/urgency", headers=owner_headers)).json()
    rose = next(u for u in urgency if u["name"] == "Hồng")
    assert (rose["surplus"], rose["discount_pct"]) == (4, 0)
    assert (await shop_prices(client))["Toàn Hồng"] == (0, 400_000)

    await setup["add_batch"](setup["rose"], 1, days_ago=6.3)  # 5 cành -> đủ ngưỡng
    await run_recompute(client, owner_headers)
    assert (await shop_prices(client))["Toàn Hồng"] == (10, 360_000)

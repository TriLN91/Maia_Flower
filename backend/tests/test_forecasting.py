from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import DemandForecast, FlowerType, UrgencyScore
from app.seed.demo import seed_demo
from app.services import forecasting
from app.services.forecast_model import (
    HolidayRule,
    backtest,
    factor_fn,
    forecast_day,
    holiday_factor,
    mape,
    restock_quantity,
    wape,
)
from app.services.inventory import utcnow

VAL = HolidayRule("Valentine", 3.0, month_day="02-14")
TET = HolidayRule("Tết", 0.3, start_date=date(2026, 2, 17), end_date=date(2026, 2, 20))
ROSE_VAL = HolidayRule("Valentine hồng", 7.0, month_day="02-14", flower_type_id=1)


def weekly(start: date, days: int, pattern=(10, 10, 10, 10, 15, 20, 18), spikes=None):
    """Lịch sử có mẫu theo thứ hoàn hảo, kèm các ngày lễ (nhân hệ số)."""
    spikes = spikes or {}
    out = {}
    for k in range(days):
        d = start + timedelta(days=k)
        out[d] = pattern[d.weekday()] * spikes.get(d, 1.0)
    return out


# ================================================================ Hệ số lễ
def test_holiday_factor_precedence():
    rules = [VAL, TET, ROSE_VAL, HolidayRule("Khác", 2.0, month_day="02-14")]
    assert holiday_factor(rules, date(2026, 2, 14), 1) == (7.0, "Valentine hồng")  # riêng thắng
    assert holiday_factor(rules, date(2026, 2, 14), 2) == (3.0, "Valentine")  # chung: lấy max
    assert holiday_factor(rules, date(2026, 2, 18), 2) == (0.3, "Tết")  # khoảng ngày
    assert holiday_factor(rules, date(2026, 2, 21), 2) == (1.0, None)


# ================================================================ Dự báo
def test_forecast_uses_same_weekday_and_holiday_multiplier():
    hist = weekly(date(2025, 12, 1), 70)
    fn = factor_fn([VAL], 2)
    origin = date(2026, 2, 9)  # thứ Hai
    sat = forecast_day(hist, origin, date(2026, 2, 14), fn)  # thứ Bảy + Valentine
    assert (sat.base, sat.multiplier, sat.holiday, sat.points) == (20, 3.0, "Valentine", 8)
    assert sat.predicted == 60
    assert forecast_day(hist, origin, date(2026, 2, 10), fn).predicted == 10  # thứ Ba


def test_history_is_deseasonalized():
    """Một ngày 14/2 trong lịch sử (bán gấp 3) không làm phồng dự báo các thứ Bảy sau đó."""
    start = date(2026, 1, 5)
    hist = weekly(start, 63, spikes={date(2026, 2, 14): 3.0})
    fn = factor_fn([VAL], 2)
    nxt_sat = forecast_day(hist, date(2026, 3, 9), date(2026, 3, 14), fn)
    assert nxt_sat.predicted == pytest.approx(20)


def test_new_shop_with_little_history_falls_back_to_recent_mean():
    hist = {date(2026, 3, 1) + timedelta(days=k): 7.0 for k in range(10)}
    f = forecast_day(hist, date(2026, 3, 11), date(2026, 3, 20), factor_fn([], 1))
    assert (f.predicted, f.points) == (7.0, 10)
    empty = forecast_day({}, date(2026, 3, 11), date(2026, 3, 20), factor_fn([], 1))
    assert (empty.predicted, empty.points) == (0, 0)


def test_restock_quantity():
    assert restock_quantity(100, 30, 15) == 90  # 115 − 30 = 85 -> làm tròn lên bó 10
    assert restock_quantity(40, 60, 15) == 0  # tồn còn đủ
    assert restock_quantity(41, 0, 0, bundle=20) == 60


def test_error_metrics():
    pairs = [(10, 8), (0, 2), (5, 5)]
    assert wape(pairs) == pytest.approx(100 * 4 / 15, abs=0.01)
    assert mape(pairs) == 10.0  # bỏ ngày thực tế = 0: (0,2 + 0) / 2
    assert wape([(0, 1)]) is None


def test_backtest_on_perfect_weekly_pattern():
    hist = {1: weekly(date(2025, 10, 6), 120)}
    origins = [date(2026, 1, 5) + timedelta(days=k) for k in range(21)]
    r = backtest(hist, [], origins, horizon=7)
    assert r.model.wape == 0
    assert r.naive_last_week.wape == 0
    assert r.moving_avg_14.wape > 15  # TB 14 ngày không bắt được mẫu theo thứ


# ================================================================ Tích hợp
async def test_forecast_backtest_and_restock_on_simulated_data(client, owner_headers):
    """Dữ liệu mô phỏng 100 ngày tới hôm qua: mô hình phải thắng 'cùng thứ tuần trước'."""
    async with SessionLocal() as s:
        await seed_demo(s, days=100, seed=11)

    r = await client.post("/api/v1/admin/forecast/recompute", headers=owner_headers)
    async with SessionLocal() as s:
        flowers = await s.scalar(select(func.count()).select_from(FlowerType))
    assert r.json() == {"rows": flowers * 14}

    fc = (await client.get("/api/v1/admin/forecast", headers=owner_headers)).json()
    assert len(fc) == flowers and len(fc[0]["days"]) == 14
    assert fc[0]["total"] > 0

    bt = (
        await client.get(
            "/api/v1/admin/forecast/backtest", params={"days": 28}, headers=owner_headers
        )
    ).json()
    assert bt["model"]["points"] == 28 * 7 * flowers
    assert bt["model"]["wape"] < bt["naive_last_week"]["wape"]
    assert bt["per_flower"]

    restock = (await client.get("/api/v1/admin/restock-suggestions", headers=owner_headers)).json()
    assert len(restock) == flowers
    vase = dict((await _vase_lives()).items())
    for line in restock:
        assert line["suggested_qty"] % 10 == 0 and line["suggested_qty"] >= 0
        assert line["cover_days"] <= vase[line["name"]]
        assert line["est_cost"] == line["est_unit_cost"] * line["suggested_qty"]


async def _vase_lives():
    async with SessionLocal() as s:
        return dict((await s.execute(select(FlowerType.name, FlowerType.vase_life_days))).all())


async def test_pricing_uses_stored_forecast(client, owner_headers):
    """Có dự báo -> bộ máy giảm giá dùng dự báo thay cho TB 14 ngày."""
    r = await client.post(
        "/api/v1/admin/flower-types",
        json={"name": "Hồng", "color": "đỏ", "vase_life_days": 7},
        headers=owner_headers,
    )
    rose = r.json()["id"]
    sup = (
        await client.post("/api/v1/admin/suppliers", json={"name": "NCC"}, headers=owner_headers)
    ).json()["id"]
    await client.post(
        "/api/v1/admin/batches",
        json={
            "flower_type_id": rose,
            "supplier_id": sup,
            "quantity": 100,
            "cost_per_stem": 8000,
            "received_at": (datetime.now(UTC) - timedelta(days=6)).isoformat(),
        },
        headers=owner_headers,
    )
    today = forecasting.local_today(utcnow())
    async with SessionLocal() as s:
        s.add_all(
            DemandForecast(
                flower_type_id=rose,
                target_date=today + timedelta(days=k),
                predicted_qty=24,
                base_qty=24,
                multiplier=1,
                holiday=None,
                history_days=56,
                model_version="t",
            )
            for k in range(4)
        )
        await s.commit()

    await client.post("/api/v1/admin/pricing/recompute", headers=owner_headers)
    async with SessionLocal() as s:
        u = await s.get(UrgencyScore, rose)
    assert u.expected_demand == pytest.approx(48, abs=0.01)  # 24 cành/ngày × 2 ngày
    assert (u.expiring_qty, u.surplus) == (100, 52)


async def test_holiday_crud_and_validation(client, owner_headers, make_staff, login):
    url = "/api/v1/admin/holiday-factors"
    r = await client.post(
        url,
        json={"name": "Lễ tình nhân", "multiplier": 3, "month_day": "02-14"},
        headers=owner_headers,
    )
    assert r.status_code == 201
    hid = r.json()["id"]

    for bad in (
        {"name": "x", "multiplier": 2},  # thiếu cả hai kiểu ngày
        {
            "name": "x",
            "multiplier": 2,
            "month_day": "02-14",
            "start_date": "2026-02-14",
            "end_date": "2026-02-14",
        },  # có cả hai
        {"name": "x", "multiplier": 2, "month_day": "14/02"},
        {"name": "x", "multiplier": 2, "start_date": "2026-02-20", "end_date": "2026-02-10"},
        {"name": "x", "multiplier": 0, "month_day": "02-14"},
    ):
        assert (await client.post(url, json=bad, headers=owner_headers)).status_code == 422, bad

    r = await client.put(
        f"{url}/{hid}",
        json={"name": "Valentine", "multiplier": 3.5, "month_day": "02-14"},
        headers=owner_headers,
    )
    assert r.json()["multiplier"] == 3.5

    await make_staff(email="tho@maiaflower.vn")
    staff = await login("tho@maiaflower.vn")
    assert (await client.get(url, headers=staff)).status_code == 200
    assert (await client.delete(f"{url}/{hid}", headers=staff)).status_code == 403
    assert (await client.delete(f"{url}/{hid}", headers=owner_headers)).status_code == 204
    assert (await client.get(url, headers=owner_headers)).json() == []

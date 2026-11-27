import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.core.db import SessionLocal
from app.models import Batch, BatchStatus, Order, OrderStatus
from app.seed.demo import SeedError, seed_demo
from app.services.inventory import ledger_audit, mark_expired_batches, utcnow

# Mô phỏng 3 tuần quanh Valentine; "now" cố định -> mọi đơn đã giao xong, kết quả tái lập được
END = date(2026, 2, 21)
NOW = datetime(2026, 2, 23, 12, 0, tzinfo=UTC)  # sau khung giao muộn nhất của 22/2


async def run_seed(**kw):
    async with SessionLocal() as s:
        return await seed_demo(s, days=21, end_date=END, seed=7, now=NOW, **kw)


async def test_seed_produces_consistent_data():
    report = await run_seed()
    assert report.orders > 200
    assert report.stems_wasted > 0
    assert 0 < report.waste_pct < 40

    async with SessionLocal() as s:
        checked, mismatches = await ledger_audit(s)
        assert checked == report.batches
        assert mismatches == []  # tồn kho = tổng sổ kho trên mọi lô
        assert await s.scalar(select(func.min(Batch.quantity_available))) >= 0
        statuses = set((await s.scalars(select(Order.status).distinct())).all())
        assert statuses == {OrderStatus.COMPLETED}


async def test_future_deliveries_stay_paid_and_hold_slots():
    """'now' = tối 21/2: đơn giao ngày 22/2 chưa giao -> PAID, vẫn chiếm chỗ khung giờ."""
    async with SessionLocal() as s:
        await seed_demo(s, days=21, end_date=END, seed=7, now=datetime(2026, 2, 21, 14, tzinfo=UTC))
        paid = (await s.scalars(select(Order).where(Order.status == OrderStatus.PAID))).all()
        assert paid
        assert all(o.delivery_ends_at > datetime(2026, 2, 21, 14, tzinfo=UTC) for o in paid)
        from app.models import DeliverySlotDay

        reserved = await s.scalar(
            select(func.sum(DeliverySlotDay.reserved_count)).where(
                DeliverySlotDay.date == date(2026, 2, 22)
            )
        )
        assert reserved >= len(paid)


async def test_seed_has_valentine_spike():
    report = await run_seed()
    normal = [n for d, n in report.orders_by_day.items() if abs((d - date(2026, 2, 14)).days) > 2]
    avg = sum(normal) / len(normal)
    assert report.orders_by_day[date(2026, 2, 14)] > 3 * avg


async def test_seed_is_deterministic():
    first = await run_seed()
    second = await run_seed(reset=True)
    assert (first.orders, first.revenue, first.stems_wasted) == (
        second.orders,
        second.revenue,
        second.stems_wasted,
    )


async def test_seed_refuses_to_overwrite_without_reset():
    await run_seed()
    with pytest.raises(SeedError, match="--reset"):
        await run_seed()


async def test_api_keeps_working_after_seed(client, owner_headers):
    """Sequence đã được đặt lại: tạo bản ghi mới qua API không đụng id của dữ liệu seed."""
    await run_seed()
    r = await client.post(
        "/api/v1/admin/flower-types",
        json={"name": "Hoa mới", "color": "đỏ", "vase_life_days": 5},
        headers=owner_headers,
    )
    assert r.status_code == 201
    audit = (await client.get("/api/v1/admin/inventory/audit", headers=owner_headers)).json()
    assert audit["ok"] is True
    assert audit["batches_checked"] > 0


# ---------------------------------------------------------------- job đêm
async def test_mark_expired_batches(client, owner_headers):
    await run_seed()
    async with SessionLocal() as s:
        # Đẩy một lô đang bán về quá khứ để nó quá hạn
        batch_id = await s.scalar(
            select(Batch.id).where(Batch.status == BatchStatus.ACTIVE, Batch.quantity_available > 0)
        )
        await s.execute(
            update(Batch)
            .where(Batch.id == batch_id)
            .values(expected_expiry_at=utcnow() - timedelta(hours=1))
        )
        await s.commit()

    async with SessionLocal() as s:
        assert await mark_expired_batches(s) >= 1
        assert (await s.get(Batch, batch_id)).status == BatchStatus.NEEDS_REVIEW
        assert await mark_expired_batches(s) == 0  # chạy lại không đổi gì

    r = await client.get(
        "/api/v1/admin/batches", params={"status": "needs_review"}, headers=owner_headers
    )
    assert batch_id in [b["id"] for b in r.json()]


async def test_nightly_celery_task_runs():
    from app.workers.tasks import mark_expired_batches_task

    assert await asyncio.to_thread(mark_expired_batches_task.run) == 0


# ---------------------------------------------------------------- chế độ demo
async def test_demo_auto_restock_follows_suggestions(client, owner_headers):
    from app.services.demo import auto_restock
    from app.services.forecasting import local_today, restock_suggestions

    async with SessionLocal() as s:
        await seed_demo(s, days=70, seed=3)
    async with SessionLocal() as s:
        expected = [
            line
            for line in await restock_suggestions(s, utcnow(), local_today(utcnow()))
            if line.suggested_qty > 0
        ]
        before = await s.scalar(select(func.count()).select_from(Batch))
        assert await auto_restock(s, utcnow()) == len(expected) > 0
        assert await s.scalar(select(func.count()).select_from(Batch)) == before + len(expected)
        checked, mismatches = await ledger_audit(s)
        assert mismatches == []


async def test_demo_restock_task_is_noop_outside_demo_mode():
    from app.workers.tasks import demo_auto_restock

    assert await asyncio.to_thread(demo_auto_restock.run) == 0


# ---------------------------------------------------------------- CLI (tiến trình thật)
async def _cli(*args: str, **env: str) -> tuple[int, str]:
    import os
    import sys

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.cli",
        *args,
        env={**os.environ, **env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode()


async def test_cli_seed_demo_if_empty_and_demo_accounts():
    """Bắt lỗi thật đã gặp khi chạy image production: lệnh seed không làm gì mà vẫn exit 0."""
    code, out = await _cli(
        "seed-demo",
        "--days",
        "10",
        "--if-empty",
        "--demo-accounts",
        DEMO_ACCOUNT_PASSWORD="demo-pass-for-tests",
    )
    assert code == 0, out
    assert "Seeded" in out and "demo accounts created" in out
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(Order)) > 0

    code, out = await _cli("seed-demo", "--if-empty")
    assert code == 0 and "already present" in out


async def test_cli_refuses_seed_in_production_without_demo_mode():
    code, out = await _cli("seed-demo", "--days", "5", APP_ENV="production", DEMO_MODE="false")
    assert code != 0 and "Refusing" in out


async def test_cli_wait_db_succeeds_when_database_is_up():
    code, out = await _cli("wait-db", "--timeout", "10")
    assert code == 0 and "Database is ready" in out


async def test_cli_wait_db_explains_unresolvable_host():
    """Đúng lỗi đã gặp trên Render: database khác region -> tên máy không phân giải được."""
    code, out = await _cli(
        "wait-db",
        "--timeout",
        "1",
        DATABASE_URL="postgresql://u:p@dpg-does-not-exist-a:5432/x",
    )
    assert code != 0
    assert "SAME region" in out and "gaierror" in out

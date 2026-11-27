"""Lệnh quản trị.

Sinh dữ liệu demo 12 tháng (xóa dữ liệu kinh doanh cũ):
    python -m app.cli seed-demo --reset [--days 365] [--seed 42] [--demo-accounts]
(--demo-accounts tạo owner@maiaflower.vn + tho@maiaflower.vn, mật khẩu lấy từ biến
 DEMO_ACCOUNT_PASSWORD — chỉ dùng cho máy dev / bản demo.)

Tạo tài khoản chủ shop đầu tiên:
    python -m app.cli create-owner --email owner@maiaflower.vn --name "Chủ shop"
(Mật khẩu được hỏi ẩn, không hiện trên màn hình và không lưu vào lịch sử lệnh.)
"""

import argparse
import asyncio
import getpass
import sys
import time
from datetime import date

from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.core.errors import AppError
from app.models.staff_user import StaffRole, StaffUser
from app.schemas.staff import StaffCreate
from app.seed.demo import SeedError, seed_demo
from app.services.inventory import ledger_audit
from app.services.staff import create_staff


async def _create_owner(email: str, name: str, password: str) -> None:
    try:
        data = StaffCreate(email=email, full_name=name, password=password, role=StaffRole.OWNER)
    except ValidationError as e:
        sys.exit(f"Invalid input: {e}")
    async with SessionLocal() as session:
        try:
            user = await create_staff(session, data)
        except AppError as e:
            sys.exit(e.message)
    await engine.dispose()
    print(f"Created owner #{user.id} <{user.email}>")


async def _ensure_demo_accounts(session) -> list[str]:
    password = get_settings().demo_account_password
    if not password:
        sys.exit("Set DEMO_ACCOUNT_PASSWORD to create demo accounts")
    created = []
    for email, name, role in [
        ("owner@maiaflower.vn", "Chủ shop (demo)", StaffRole.OWNER),
        ("tho@maiaflower.vn", "Thợ bó (demo)", StaffRole.STAFF),
    ]:
        if await session.scalar(select(StaffUser.id).where(StaffUser.email == email)) is None:
            await create_staff(
                session, StaffCreate(email=email, full_name=name, password=password, role=role)
            )
            created.append(email)
    return created


async def _seed_demo(
    days: int, end_date: date | None, seed: int, reset: bool, demo_accounts: bool
) -> None:
    started = time.perf_counter()
    async with SessionLocal() as session:
        try:
            r = await seed_demo(session, days=days, end_date=end_date, seed=seed, reset=reset)
        except SeedError as e:
            sys.exit(str(e))
        checked, mismatches = await ledger_audit(session)
        accounts = await _ensure_demo_accounts(session) if demo_accounts else []
    await engine.dispose()
    busiest = sorted(r.orders_by_day.items(), key=lambda kv: kv[1], reverse=True)[:5]
    print(f"Seeded {r.start_date} → {r.end_date} in {time.perf_counter() - started:.1f}s")
    print(
        f"  orders: {r.orders:,} ({r.bouquets:,} bouquets), lost (out of stock): {r.lost_orders:,}"
    )
    print(f"  revenue (flowers): {r.revenue:,} VND")
    print(
        f"  batches: {r.batches:,}, stems imported: {r.stems_imported:,}, "
        f"wasted: {r.stems_wasted:,} ({r.waste_pct}%)"
    )
    print("  busiest days: " + ", ".join(f"{d} ({n})" for d, n in busiest))
    print(f"  ledger audit: {checked:,} batches, {len(mismatches)} mismatches")
    if accounts:
        print("  demo accounts created: " + ", ".join(accounts))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    owner = sub.add_parser("create-owner", help="Tạo tài khoản chủ shop")
    owner.add_argument("--email", required=True)
    owner.add_argument("--name", required=True)
    demo = sub.add_parser("seed-demo", help="Sinh dữ liệu demo mô phỏng N ngày bán hàng")
    demo.add_argument("--days", type=int, default=365)
    demo.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=None,
        help="Ngày cuối (YYYY-MM-DD), mặc định hôm qua (giờ VN)",
    )
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument(
        "--reset",
        action="store_true",
        help="XÓA toàn bộ dữ liệu kinh doanh (giữ tài khoản, khung giờ, cài đặt)",
    )
    demo.add_argument(
        "--demo-accounts",
        action="store_true",
        help="Tạo tài khoản demo (mật khẩu từ DEMO_ACCOUNT_PASSWORD)",
    )
    args = parser.parse_args()

    if args.command == "create-owner":
        password = getpass.getpass("Password (min 8 chars): ")
        if password != getpass.getpass("Confirm password: "):
            sys.exit("Passwords do not match")
        asyncio.run(_create_owner(args.email, args.name, password))
    elif args.command == "seed-demo":
        if get_settings().app_env == "production":
            sys.exit("Refusing to seed demo data in production")
        asyncio.run(_seed_demo(args.days, args.end_date, args.seed, args.reset, args.demo_accounts))


if __name__ == "__main__":
    main()

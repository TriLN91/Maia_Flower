"""Lệnh quản trị.

Tạo tài khoản chủ shop đầu tiên:
    python -m app.cli create-owner --email owner@maiaflower.vn --name "Chủ shop"
(Mật khẩu được hỏi ẩn, không hiện trên màn hình và không lưu vào lịch sử lệnh.)
"""

import argparse
import asyncio
import getpass
import sys

from pydantic import ValidationError

from app.core.db import SessionLocal, engine
from app.core.errors import AppError
from app.models.staff_user import StaffRole
from app.schemas.staff import StaffCreate
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    owner = sub.add_parser("create-owner", help="Tạo tài khoản chủ shop")
    owner.add_argument("--email", required=True)
    owner.add_argument("--name", required=True)
    args = parser.parse_args()

    if args.command == "create-owner":
        password = getpass.getpass("Password (min 8 chars): ")
        if password != getpass.getpass("Confirm password: "):
            sys.exit("Passwords do not match")
        asyncio.run(_create_owner(args.email, args.name, password))


if __name__ == "__main__":
    main()

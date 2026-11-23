import os

# Phải đặt TRƯỚC khi import app: engine của app đọc DATABASE_URL lúc import.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL is not set — refusing to run tests on the dev database")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "test"
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)

from collections.abc import AsyncIterator, Awaitable, Callable  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, StaffRole, StaffUser  # noqa: E402
from app.schemas.staff import StaffCreate  # noqa: E402
from app.services.staff import create_staff  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PASSWORD = "flower-pass-123"


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Chạy migration thật (downgrade về gốc rồi upgrade) -> kiểm tra luôn migration."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def clean_tables(migrated_database: None) -> AsyncIterator[None]:
    yield
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with SessionLocal() as session:
        await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await session.commit()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


MakeStaff = Callable[..., Awaitable[StaffUser]]


@pytest.fixture
def make_staff() -> MakeStaff:
    async def _make(
        email: str = "staff@maiaflower.vn",
        role: StaffRole = StaffRole.STAFF,
        password: str = DEFAULT_PASSWORD,
        full_name: str = "Test User",
    ) -> StaffUser:
        async with SessionLocal() as session:
            return await create_staff(
                session,
                StaffCreate(email=email, full_name=full_name, password=password, role=role),
            )

    return _make


@pytest.fixture
def login(client: AsyncClient) -> Callable[..., Awaitable[dict[str, str]]]:
    """Đăng nhập và trả về header Authorization."""

    async def _login(email: str, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
        r = await client.post("/api/v1/auth/login", data={"username": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login


@pytest.fixture
async def owner_headers(make_staff: MakeStaff, login) -> dict[str, str]:
    await make_staff(email="owner@maiaflower.vn", role=StaffRole.OWNER)
    return await login("owner@maiaflower.vn")

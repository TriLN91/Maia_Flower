from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import mount_frontend

SECRET = "x" * 40


def make(**kw) -> Settings:
    return Settings(jwt_secret=SECRET, _env_file=None, **kw)


def test_render_database_url_is_converted_to_asyncpg():
    s = make(database_url="postgres://u:p@dpg-abc:5432/maia?sslmode=require&application_name=x")
    assert s.database_url == "postgresql+asyncpg://u:p@dpg-abc:5432/maia?application_name=x"
    s = make(database_url="postgresql://u:p@h/db")
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    s = make(database_url="postgresql+asyncpg://u:p@h/db")
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"


def test_production_defaults():
    prod = make(app_env="production", public_base_url="https://maia.onrender.com/")
    assert prod.mock_gateway_enabled is False  # production không tự bật cổng giả lập
    assert prod.public_base_url == "https://maia.onrender.com"
    demo = make(app_env="production", mock_gateway_enabled=True)
    assert demo.mock_gateway_enabled is True
    assert make().mock_gateway_enabled is True  # dev


def test_same_origin_web_sets_payment_return_url():
    s = make(public_base_url="https://maia.onrender.com", frontend_dist_dir="/app/static")
    assert s.payment_return_url == "https://maia.onrender.com/payment-result"
    assert make(public_base_url="https://x").payment_return_url is None


def test_render_external_url_is_used(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://maia-flower.onrender.com")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    assert make().public_base_url == "https://maia-flower.onrender.com"


async def test_spa_serving(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (tmp_path / "assets" / "main.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("nope", encoding="utf-8")

    app = FastAPI()

    @app.get("/api/v1/health")
    def health():
        return {"ok": True}

    mount_frontend(app, tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/")).text == "<html>app</html>"
        deep = await c.get("/admin/kho")  # đường dẫn của React Router -> index.html
        assert deep.text == "<html>app</html>"
        assert deep.headers["cache-control"] == "no-cache"
        assert (await c.get("/assets/main.js")).text == "console.log(1)"
        assert (await c.get("/api/v1/health")).json() == {"ok": True}
        assert (await c.get("/api/v1/khong-ton-tai")).status_code == 404  # API không trả HTML
        assert (await c.get("/docs-xyz")).status_code == 404
        traversal = await c.get("/..%2Fsecret.txt")
        assert "nope" not in traversal.text

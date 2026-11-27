from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import register_error_handlers


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Shop hoa bó: tồn kho theo lô (FEFO), giảm giá động, dự báo nhu cầu.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(api_router)
    if settings.payment_provider == "mock" and settings.mock_gateway_enabled:
        from app.api.mock_gateway import router as mock_gateway_router

        app.include_router(mock_gateway_router)
    if settings.frontend_dist_dir:
        mount_frontend(app, Path(settings.frontend_dist_dir))
    elif settings.frontend_url:
        # API và web tách riêng: ai mở thẳng URL của API thì đưa sang web
        @app.get("/", include_in_schema=False)
        def to_frontend() -> RedirectResponse:
            return RedirectResponse(settings.frontend_url, status_code=307)

    return app


# Đường dẫn thuộc về backend — không bao giờ trả index.html cho chúng
_BACKEND_PREFIXES = ("api/", "mock-gateway", "docs", "redoc", "openapi.json")


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Phục vụ bản build Vite: /assets (tên có hash -> cache lâu) + fallback SPA về index.html
    cho mọi đường dẫn còn lại (/, /mau/…, /admin/…)."""
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"FRONTEND_DIST_DIR={dist} has no index.html")
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    root = dist.resolve()

    # Hàm thường (không async): FastAPI chạy trong thread pool, thao tác file không chặn event loop
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(_BACKEND_PREFIXES):
            raise HTTPException(404)
        file = (root / path).resolve()
        # chặn ../ thoát khỏi thư mục build
        if path and file.is_relative_to(root) and file.is_file():
            return FileResponse(file)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()

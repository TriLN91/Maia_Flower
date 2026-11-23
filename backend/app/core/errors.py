from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Lỗi nghiệp vụ. Tầng service ném ra, handler chung chuyển thành JSON:

        {"detail": "<thông điệp cho người>", "code": "<MÃ_CHO_MÁY>", "extra": {...}}

    Frontend dựa vào `code` để xử lý (vd. OUT_OF_STOCK -> báo hết hàng),
    không phải phân tích chuỗi `detail`.
    """

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.extra = extra or {}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {"detail": exc.message, "code": exc.code}
        if exc.extra:
            body["extra"] = exc.extra
        return JSONResponse(status_code=exc.status_code, content=body)

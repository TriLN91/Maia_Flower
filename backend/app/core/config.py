import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# .env nằm ở thư mục gốc repo (cạnh docker-compose.yml)
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Maia_Flower API"
    app_env: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+asyncpg://maia:maia_dev_password@localhost:5432/maia_flower"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=60, ge=1)

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Giới hạn tần suất (Redis). Tắt được khi chạy test tải nội bộ.
    rate_limit_enabled: bool = True
    # Chỉ bật khi API đứng sau reverse proxy tin cậy (Render/Nginx): lấy IP thật từ
    # X-Forwarded-For. Bật khi KHÔNG có proxy = cho phép khách tự giả IP để lách giới hạn.
    trust_proxy_headers: bool = False

    # --- Đặt hàng & giao hàng ---
    shop_timezone: str = "Asia/Ho_Chi_Minh"
    # Phải đặt trước giờ bắt đầu khung giao ít nhất bấy nhiêu phút (để kịp bó hoa)
    order_lead_time_minutes: int = Field(default=120, ge=0)
    # Đặt trước tối đa bao nhiêu ngày
    booking_window_days: int = Field(default=7, ge=1, le=60)
    # Thời gian giữ hoa + khung giờ chờ khách thanh toán
    hold_minutes: int = Field(default=15, ge=1, le=120)
    # Báo giá ship có hiệu lực trong bấy nhiêu phút
    delivery_quote_minutes: int = Field(default=15, ge=1, le=120)

    # --- Thanh toán ---
    # "mock" = cổng giả lập trong app (ký HMAC-SHA512 y như VNPay). Sau này thêm "vnpay".
    payment_provider: Literal["mock"] = "mock"
    # Khóa ký giữa shop và cổng thanh toán (giả lập vnp_HashSecret). Production phải đặt riêng.
    mock_pay_secret: str = Field(
        default="dev-only-mock-gateway-secret-change-me-0000", min_length=32
    )
    # URL công khai của API (cổng thanh toán redirect/IPN về đây).
    # Trên Render tự lấy từ RENDER_EXTERNAL_URL nếu không đặt.
    public_base_url: str = Field(
        default_factory=lambda: os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8000")
    )
    # Trang kết quả thanh toán của frontend; trống = trả JSON ở API (dùng khi chưa có web)
    payment_return_url: str | None = None
    # Bật cổng thanh toán giả lập. Trống = bật khi không phải production.
    # Bản demo công khai đặt true (vẫn là production, chỉ là không có cổng thật).
    mock_gateway_enabled: bool | None = None
    # URL của web khi web và API khác origin (vd. Static Site riêng trên Render).
    # Có -> tự thêm vào CORS, trang kết quả thanh toán về web, `/` của API chuyển sang web.
    frontend_url: str | None = None
    # Thư mục bản build frontend (Vite `dist`). Có = FastAPI phục vụ luôn web (1 dịch vụ).
    frontend_dist_dir: str | None = None
    # Bản demo công khai: cho phép seed khi production, tự nhập hàng mỗi sáng.
    demo_mode: bool = False
    # Mật khẩu tài khoản demo (seed-demo --demo-accounts). KHÔNG dùng cho tài khoản thật.
    demo_account_password: str | None = None

    # --- Bản đồ (Goong). Không có key -> tính đường chim bay × hệ số đường vòng ---
    goong_api_key: str | None = None
    goong_base_url: str = "https://rsapi.goong.io"
    goong_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    # Quãng đường thực tế ≈ đường chim bay × hệ số này (dùng khi không gọi được Goong)
    road_factor: float = Field(default=1.3, ge=1, le=3)

    @field_validator("database_url", mode="before")
    @classmethod
    def asyncpg_url(cls, value: object) -> object:
        """Render/Heroku đưa `postgres://…` hoặc `postgresql://…` -> đổi sang driver asyncpg;
        bỏ `sslmode` (asyncpg không nhận tham số này qua URL; mạng nội bộ không cần SSL)."""
        if not isinstance(value, str):
            return value
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                value = "postgresql+asyncpg://" + value[len(prefix) :]
        parts = urlsplit(value)
        query = [(k, v) for k, v in parse_qsl(parts.query) if k != "sslmode"]
        return urlunsplit(parts._replace(query=urlencode(query)))

    @model_validator(mode="after")
    def _derived(self) -> "Settings":
        self.public_base_url = self.public_base_url.rstrip("/")
        if self.mock_gateway_enabled is None:
            self.mock_gateway_enabled = self.app_env != "production"
        if self.frontend_url:
            self.frontend_url = self.frontend_url.rstrip("/")
            if self.frontend_url not in self.cors_origins:
                self.cors_origins = [*self.cors_origins, self.frontend_url]
        # Cổng thanh toán trả khách về trang kết quả của web (web riêng hoặc cùng origin)
        if self.payment_return_url is None:
            if self.frontend_url:
                self.payment_return_url = f"{self.frontend_url}/payment-result"
            elif self.frontend_dist_dir:
                self.payment_return_url = f"{self.public_base_url}/payment-result"
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
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

    # --- Bản đồ (Goong). Không có key -> tính đường chim bay × hệ số đường vòng ---
    goong_api_key: str | None = None
    goong_base_url: str = "https://rsapi.goong.io"
    goong_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    # Quãng đường thực tế ≈ đường chim bay × hệ số này (dùng khi không gọi được Goong)
    road_factor: float = Field(default=1.3, ge=1, le=3)

    # --- Kho & định giá (ngày 8 sẽ chuyển sang bảng shop_settings để chủ shop sửa trên web) ---
    # Lô hết hạn trong số ngày này được tính là "sắp hết hạn"
    expiring_soon_days: int = Field(default=2, ge=1, le=14)
    # Trần giảm giá động cho một mẫu (%)
    max_discount_pct: int = Field(default=30, ge=0, le=90)
    # Biên lợi nhuận tối thiểu trên giá vốn (%) — giá bán sau giảm không được thấp hơn
    min_margin_pct: int = Field(default=20, ge=0, le=500)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

import re
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.schemas.common import Money


def _mm_dd(value: str) -> str:
    if not re.fullmatch(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", value):
        raise ValueError("Holiday must be in MM-DD format, e.g. 02-14")
    return value


class FeeTier(BaseModel):
    """Từ hết bậc trước tới `to_km`: mỗi km tính `per_km` đồng."""

    to_km: Annotated[float, Field(gt=0, le=100)]
    per_km: Money


class DeliverySettings(BaseModel):
    shop_address: Annotated[str, Field(max_length=300)] = "Chợ Bến Thành, Quận 1, TP.HCM"
    shop_lat: Annotated[float, Field(ge=-90, le=90)] = 10.7725
    shop_lng: Annotated[float, Field(ge=-180, le=180)] = 106.6980

    base_km: Annotated[float, Field(ge=0, le=50)] = 3
    base_fee: Money = 20_000
    tiers: Annotated[list[FeeTier], Field(min_length=1, max_length=10)] = [
        FeeTier(to_km=10, per_km=5_000),
        FeeTier(to_km=15, per_km=7_000),
    ]
    max_km: Annotated[float, Field(gt=0, le=100)] = 15

    holiday_surcharge_pct: Annotated[int, Field(ge=0, le=200)] = 20
    holidays: list[Annotated[str, AfterValidator(_mm_dd)]] = [
        "02-14",
        "03-08",
        "10-20",
        "11-20",
        "12-24",
    ]

    free_ship_min_subtotal: Money | None = 1_500_000
    free_ship_max_km: Annotated[float, Field(ge=0, le=100)] = 5

    @model_validator(mode="after")
    def _tiers_cover_range(self) -> Self:
        edges = [self.base_km, *(t.to_km for t in self.tiers)]
        if any(b <= a for a, b in zip(edges, edges[1:], strict=False)):
            raise ValueError("Tier to_km values must be strictly increasing and above base_km")
        if self.tiers[-1].to_km < self.max_km:
            raise ValueError("Last tier must reach max_km")
        return self


class DiscountTier(BaseModel):
    """Lô còn ≤ `days_left_max` ngày (và đang dư thừa) -> loại hoa đó được giảm `pct`%."""

    days_left_max: Annotated[float, Field(gt=0, le=14)]
    pct: Annotated[int, Field(ge=0, le=90)]


class PricingSettings(BaseModel):
    # Công tắc tổng: tắt = mọi mẫu về giá gốc ngay lập tức
    enabled: bool = True
    # Lô hết hạn trong số ngày này được tính là "sắp hết hạn"
    horizon_days: Annotated[float, Field(gt=0, le=14)] = 2
    tiers: Annotated[list[DiscountTier], Field(min_length=1, max_length=10)] = [
        DiscountTier(days_left_max=2, pct=10),
        DiscountTier(days_left_max=1, pct=20),
    ]
    max_discount_pct: Annotated[int, Field(ge=0, le=90)] = 30  # trần giảm cho một mẫu
    min_margin_pct: Annotated[int, Field(ge=0, le=500)] = 20  # giá sau giảm ≥ vốn × (1 + x%)
    max_step_pct: Annotated[int, Field(ge=1, le=100)] = 10  # mỗi lần chạy đổi tối đa ±x điểm %
    demand_lookback_days: Annotated[int, Field(ge=1, le=90)] = 14  # ước lượng nhu cầu (tới ngày 9)

    @model_validator(mode="after")
    def _tiers_within_horizon(self) -> Self:
        if any(t.days_left_max > self.horizon_days for t in self.tiers):
            raise ValueError("Every tier's days_left_max must be within horizon_days")
        return self

    def flower_discount(self, days_left: float) -> int:
        """Bậc khắt khe nhất (ít ngày nhất) mà lô còn thỏa -> mức giảm lớn nhất áp dụng."""
        matching = [t.pct for t in self.tiers if days_left <= t.days_left_max]
        return max(matching, default=0)

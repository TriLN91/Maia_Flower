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

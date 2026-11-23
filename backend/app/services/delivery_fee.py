"""Tính phí ship theo quãng đường. Hàm thuần — không đụng DB/mạng nên test dễ và chắc."""

import math
from dataclasses import dataclass
from datetime import date

from app.core.errors import AppError
from app.schemas.settings import DeliverySettings


@dataclass(frozen=True)
class FeeBreakdown:
    distance_km: float  # đã làm tròn lên 0,1 km
    base_fee: int
    distance_fee: int
    holiday_surcharge: int
    free_shipping: bool
    total: int


def billable_km(distance_km: float) -> float:
    """Làm tròn LÊN tới 0,1 km (7,41 -> 7,5). Tránh lỗi số thực kiểu 7.4 -> 7.4000000001."""
    return math.ceil(round(distance_km * 10, 6)) / 10


def compute_fee(
    distance_km: float,
    *,
    settings: DeliverySettings,
    delivery_date: date | None = None,
    subtotal: int | None = None,
) -> FeeBreakdown:
    km = billable_km(distance_km)
    if km > settings.max_km:
        raise AppError(
            "Address is outside our delivery area",
            code="OUT_OF_DELIVERY_RANGE",
            extra={"distance_km": km, "max_km": settings.max_km},
        )

    distance_fee = 0.0
    lower = settings.base_km
    for tier in settings.tiers:
        if km <= lower:
            break
        distance_fee += (min(km, tier.to_km) - lower) * tier.per_km
        lower = tier.to_km
    distance_fee_int = round(distance_fee)

    fee = settings.base_fee + distance_fee_int
    surcharge = 0
    if delivery_date is not None and delivery_date.strftime("%m-%d") in settings.holidays:
        # Làm tròn phụ phí lên nghìn đồng cho giá dễ đọc
        surcharge = math.ceil(fee * settings.holiday_surcharge_pct / 100 / 1000) * 1000
        fee += surcharge

    free = (
        settings.free_ship_min_subtotal is not None
        and subtotal is not None
        and subtotal >= settings.free_ship_min_subtotal
        and km <= settings.free_ship_max_km
    )
    return FeeBreakdown(
        distance_km=km,
        base_fee=settings.base_fee,
        distance_fee=distance_fee_int,
        holiday_surcharge=surcharge,
        free_shipping=free,
        total=0 if free else fee,
    )

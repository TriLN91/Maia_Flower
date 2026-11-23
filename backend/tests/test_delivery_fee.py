from datetime import date

import pytest

from app.core.errors import AppError
from app.schemas.settings import DeliverySettings, FeeTier
from app.services.delivery_fee import billable_km, compute_fee

S = DeliverySettings()  # bảng phí mẫu: 3 km đầu 20k, km 3–10: 5k/km, km 10–15: 7k/km, tối đa 15 km


@pytest.mark.parametrize(
    ("km", "expected"),
    [
        (0.5, 20_000),
        (3.0, 20_000),
        (3.01, 20_500),  # làm tròn lên 3,1 km -> 0,1 × 5000
        (7.4, 42_000),  # ví dụ trong DESIGN.md
        (10.0, 55_000),
        (12.0, 69_000),  # ví dụ trong DESIGN.md: 20k + 7×5k + 2×7k
        (15.0, 90_000),
    ],
)
def test_fee_table_examples(km, expected):
    assert compute_fee(km, settings=S).total == expected


def test_billable_km_rounds_up_to_100m_without_float_noise():
    assert billable_km(7.4) == 7.4
    assert billable_km(7.41) == 7.5
    assert billable_km(0) == 0


def test_beyond_max_distance_is_rejected():
    with pytest.raises(AppError) as e:
        compute_fee(15.01, settings=S)
    assert e.value.code == "OUT_OF_DELIVERY_RANGE"
    assert e.value.extra == {"distance_km": 15.1, "max_km": 15}


def test_holiday_surcharge_rounded_up_to_thousand():
    fee = compute_fee(7.4, settings=S, delivery_date=date(2027, 2, 14))
    assert fee.holiday_surcharge == 9_000  # 20% × 42 000 = 8 400 -> 9 000
    assert fee.total == 51_000
    assert compute_fee(7.4, settings=S, delivery_date=date(2027, 2, 15)).holiday_surcharge == 0


@pytest.mark.parametrize(
    ("km", "subtotal", "free"),
    [
        (4.0, 1_500_000, True),
        (4.0, 1_499_999, False),
        (5.1, 2_000_000, False),  # quá 5 km
        (4.0, None, False),  # chưa biết giỏ hàng
    ],
)
def test_free_shipping_rule(km, subtotal, free):
    fee = compute_fee(km, settings=S, subtotal=subtotal)
    assert fee.free_shipping is free
    assert (fee.total == 0) is free


def test_settings_validation():
    with pytest.raises(ValueError, match="strictly increasing"):
        DeliverySettings(tiers=[FeeTier(to_km=10, per_km=1), FeeTier(to_km=8, per_km=1)])
    with pytest.raises(ValueError, match="reach max_km"):
        DeliverySettings(max_km=20)
    with pytest.raises(ValueError, match="MM-DD"):
        DeliverySettings(holidays=["14/02"])

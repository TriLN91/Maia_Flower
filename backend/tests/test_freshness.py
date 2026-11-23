from datetime import UTC, datetime, timedelta

import pytest

from app.models import BatchStatus
from app.services.inventory import compute_freshness

T0 = datetime(2026, 2, 10, 8, 0, tzinfo=UTC)
EXPIRY = T0 + timedelta(days=4)


@pytest.mark.parametrize(
    ("hours_after", "expected_freshness", "expected_days_left"),
    [
        (0, 1.0, 4.0),
        (24, 0.75, 3.0),
        (48, 0.5, 2.0),
        (96, 0.0, 0.0),
        (120, 0.0, -1.0),  # quá hạn: không âm
        (-5, 1.0, 4.21),  # đồng hồ lệch: không vượt 1
    ],
)
def test_freshness_decreases_linearly(hours_after, expected_freshness, expected_days_left):
    info = compute_freshness(
        received_at=T0, expected_expiry_at=EXPIRY, now=T0 + timedelta(hours=hours_after)
    )
    assert info.freshness == pytest.approx(expected_freshness)
    assert info.days_left == pytest.approx(expected_days_left, abs=0.01)


def test_override_can_only_lower_freshness():
    now = T0 + timedelta(days=1)  # theo thời gian: 0.75
    assert compute_freshness(
        received_at=T0, expected_expiry_at=EXPIRY, now=now, override=0.3
    ).freshness == pytest.approx(0.3)
    assert compute_freshness(
        received_at=T0, expected_expiry_at=EXPIRY, now=now, override=0.95
    ).freshness == pytest.approx(0.75)


@pytest.mark.parametrize(
    ("kwargs", "sellable"),
    [
        ({}, True),
        ({"now": EXPIRY}, False),
        ({"override": 0.0}, False),
        ({"quantity_available": 0}, False),
        ({"status": BatchStatus.NEEDS_REVIEW}, False),
        ({"status": BatchStatus.DISCARDED}, False),
    ],
)
def test_sellable_rules(kwargs, sellable):
    params = {"received_at": T0, "expected_expiry_at": EXPIRY, "now": T0 + timedelta(hours=1)}
    assert compute_freshness(**{**params, **kwargs}).is_sellable is sellable

"""Khung giờ giao hàng: tính còn chỗ / đặt được không, và khóa chỗ khi checkout."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import DeliverySlot, DeliverySlotDay


def shop_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().shop_timezone)


def slot_window(slot: DeliverySlot, day: date) -> tuple[datetime, datetime]:
    """Giờ bắt đầu/kết thúc thực (có múi giờ) của một khung trong một ngày."""
    tz = shop_tz()
    return (
        datetime.combine(day, slot.start_time, tzinfo=tz),
        datetime.combine(day, slot.end_time, tzinfo=tz),
    )


def booking_problem(slot: DeliverySlot, day: date, now: datetime) -> str | None:
    """Lý do không cho đặt khung này theo thời gian (không xét sức chứa)."""
    settings = get_settings()
    today = now.astimezone(shop_tz()).date()
    if day < today or day > today + timedelta(days=settings.booking_window_days):
        return "OUT_OF_WINDOW"
    start, _ = slot_window(slot, day)
    if start < now + timedelta(minutes=settings.order_lead_time_minutes):
        return "TOO_LATE"
    return None


@dataclass
class SlotAvailability:
    slot: DeliverySlot
    day: date
    capacity: int
    remaining: int
    reason: str | None

    @property
    def bookable(self) -> bool:
        return self.reason is None


async def availability(session: AsyncSession, day: date, now: datetime) -> list[SlotAvailability]:
    slots = (
        await session.scalars(
            select(DeliverySlot)
            .where(DeliverySlot.is_active.is_(True))
            .order_by(DeliverySlot.start_time)
        )
    ).all()
    days = {
        d.slot_id: d
        for d in (
            await session.scalars(select(DeliverySlotDay).where(DeliverySlotDay.date == day))
        ).all()
    }
    result = []
    for slot in slots:
        d = days.get(slot.id)
        capacity = d.capacity if d else slot.default_capacity
        reserved = d.reserved_count if d else 0
        remaining = max(0, capacity - reserved)
        reason = booking_problem(slot, day, now)
        if reason is None and d is not None and d.is_closed:
            reason = "CLOSED"
        if reason is None and remaining == 0:
            reason = "FULL"
        result.append(SlotAvailability(slot, day, capacity, remaining, reason))
    return result


async def reserve_slot(
    session: AsyncSession, slot_id: int, day: date, now: datetime
) -> DeliverySlotDay:
    """Khóa dòng (khung, ngày) và giữ 1 chỗ. KHÔNG commit."""
    slot = await session.get(DeliverySlot, slot_id)
    if slot is None or not slot.is_active:
        raise NotFoundError("Delivery slot not found", code="SLOT_NOT_FOUND")
    reason = booking_problem(slot, day, now)
    if reason:
        raise AppError(f"Delivery slot cannot be booked: {reason}", code=f"SLOT_{reason}")

    # Tạo dòng ngày nếu chưa có (an toàn khi nhiều người cùng tạo: ON CONFLICT DO NOTHING)
    await session.execute(
        insert(DeliverySlotDay)
        .values(slot_id=slot.id, date=day, capacity=slot.default_capacity, reserved_count=0)
        .on_conflict_do_nothing(index_elements=["slot_id", "date"])
    )
    slot_day = await session.scalar(
        select(DeliverySlotDay)
        .where(DeliverySlotDay.slot_id == slot.id, DeliverySlotDay.date == day)
        .with_for_update(of=DeliverySlotDay)
        .execution_options(populate_existing=True)
    )
    if slot_day is None:  # không thể xảy ra sau INSERT … ON CONFLICT, phòng hờ
        raise ConflictError("Delivery slot is busy, please retry", code="RETRY")
    if slot_day.is_closed:
        raise AppError("Delivery slot is closed", code="SLOT_CLOSED")
    if slot_day.reserved_count >= slot_day.capacity:
        raise ConflictError("Delivery slot is full", code="SLOT_FULL")
    slot_day.reserved_count += 1
    return slot_day

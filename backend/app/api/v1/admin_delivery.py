from collections.abc import Sequence
from datetime import date, time
from typing import Annotated, Self

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import CurrentOwner, CurrentStaff, SessionDep
from app.core.errors import AppError, NotFoundError
from app.models import DeliverySlot, DeliverySlotDay
from app.schemas.settings import DeliverySettings
from app.services.shop_settings import get_delivery_settings, save_delivery_settings

router = APIRouter(prefix="/admin")

Capacity = Annotated[int, Field(ge=0, le=500)]


# ---------------- Schemas ----------------
class SlotIn(BaseModel):
    start_time: time
    end_time: time
    default_capacity: Capacity

    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class SlotUpdate(BaseModel):
    default_capacity: Capacity | None = None
    is_active: bool | None = None


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    start_time: time
    end_time: time
    default_capacity: int
    is_active: bool


class SlotDayIn(BaseModel):
    capacity: Capacity | None = None
    is_closed: bool | None = None


class SlotDayOut(BaseModel):
    slot_id: int
    date: date
    start_time: time
    end_time: time
    capacity: int
    reserved_count: int
    is_closed: bool
    overridden: bool = Field(description="false = đang dùng sức chứa mặc định của khung")


# ---------------- Khung giờ mẫu ----------------
async def _ensure_no_overlap(session, start: time, end: time, exclude_id: int | None = None):
    stmt = select(DeliverySlot).where(
        DeliverySlot.is_active.is_(True),
        DeliverySlot.start_time < end,
        DeliverySlot.end_time > start,
    )
    if exclude_id is not None:
        stmt = stmt.where(DeliverySlot.id != exclude_id)
    clash = await session.scalar(stmt)
    if clash:
        raise AppError(
            "Slot overlaps an existing active slot",
            code="SLOT_OVERLAP",
            extra={"slot_id": clash.id},
        )


@router.get("/delivery-slots", response_model=list[SlotOut], tags=["admin: delivery"])
async def list_slots(session: SessionDep, _: CurrentStaff) -> Sequence[DeliverySlot]:
    return (await session.scalars(select(DeliverySlot).order_by(DeliverySlot.start_time))).all()


@router.post(
    "/delivery-slots",
    response_model=SlotOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: delivery"],
)
async def create_slot(session: SessionDep, _: CurrentOwner, body: SlotIn) -> DeliverySlot:
    await _ensure_no_overlap(session, body.start_time, body.end_time)
    slot = DeliverySlot(**body.model_dump())
    session.add(slot)
    await session.commit()
    return slot


@router.patch("/delivery-slots/{slot_id}", response_model=SlotOut, tags=["admin: delivery"])
async def update_slot(
    session: SessionDep, _: CurrentOwner, slot_id: int, body: SlotUpdate
) -> DeliverySlot:
    """Đổi sức chứa mặc định / bật-tắt khung. Không đổi giờ của khung đã có (đơn cũ tham chiếu
    tới nó) — muốn đổi giờ thì tắt khung cũ, tạo khung mới."""
    slot = await session.get(DeliverySlot, slot_id)
    if slot is None:
        raise NotFoundError("Delivery slot not found")
    changes = body.model_dump(exclude_unset=True)
    if any(v is None for v in changes.values()):
        raise AppError("Fields cannot be null", code="NULL_NOT_ALLOWED")
    if changes.get("is_active") is True and not slot.is_active:
        await _ensure_no_overlap(session, slot.start_time, slot.end_time, exclude_id=slot.id)
    for k, v in changes.items():
        setattr(slot, k, v)
    await session.commit()
    return slot


# ---------------- Ghi đè theo ngày ----------------
@router.get("/delivery-slot-days", response_model=list[SlotDayOut], tags=["admin: delivery"])
async def list_slot_days(
    session: SessionDep, _: CurrentStaff, day: Annotated[date, Query(alias="date")]
) -> list[SlotDayOut]:
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
    return [
        SlotDayOut(
            slot_id=s.id,
            date=day,
            start_time=s.start_time,
            end_time=s.end_time,
            capacity=days[s.id].capacity if s.id in days else s.default_capacity,
            reserved_count=days[s.id].reserved_count if s.id in days else 0,
            is_closed=days[s.id].is_closed if s.id in days else False,
            overridden=s.id in days,
        )
        for s in slots
    ]


@router.put(
    "/delivery-slots/{slot_id}/days/{day}", response_model=SlotDayOut, tags=["admin: delivery"]
)
async def override_slot_day(
    session: SessionDep, _: CurrentOwner, slot_id: int, day: date, body: SlotDayIn
) -> SlotDayOut:
    """Ngày lễ tăng sức chứa, hoặc đóng khung ngày nghỉ. Không hạ sức chứa xuống dưới số đơn
    đã giữ chỗ."""
    slot = await session.get(DeliverySlot, slot_id)
    if slot is None:
        raise NotFoundError("Delivery slot not found")

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
    if body.capacity is not None:
        if body.capacity < slot_day.reserved_count:
            raise AppError(
                "Capacity cannot be lower than orders already booked",
                code="CAPACITY_BELOW_RESERVED",
                extra={"reserved_count": slot_day.reserved_count},
            )
        slot_day.capacity = body.capacity
    if body.is_closed is not None:
        slot_day.is_closed = body.is_closed
    await session.commit()
    return SlotDayOut(
        slot_id=slot.id,
        date=day,
        start_time=slot.start_time,
        end_time=slot.end_time,
        capacity=slot_day.capacity,
        reserved_count=slot_day.reserved_count,
        is_closed=slot_day.is_closed,
        overridden=True,
    )


# ---------------- Cài đặt giao hàng ----------------
@router.get("/settings/delivery", response_model=DeliverySettings, tags=["admin: settings"])
async def get_delivery(session: SessionDep, _: CurrentOwner) -> DeliverySettings:
    return await get_delivery_settings(session)


@router.put("/settings/delivery", response_model=DeliverySettings, tags=["admin: settings"])
async def put_delivery(
    session: SessionDep, owner: CurrentOwner, body: DeliverySettings
) -> DeliverySettings:
    """Tọa độ shop, bảng phí theo km, bán kính giao, phụ phí lễ, miễn phí ship."""
    return await save_delivery_settings(session, owner, body)

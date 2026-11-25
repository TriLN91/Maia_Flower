"""Giữ và nhả hoa + khung giờ cho một đơn.

Thứ tự khóa dùng chung ở MỌI giao dịch để không bao giờ deadlock:
    (payment) -> order -> delivery_slot_day -> batches (theo flower_type_id, expected_expiry_at, id)
"""

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError
from app.models import (
    Batch,
    BatchStatus,
    DeliverySlotDay,
    FlowerType,
    MovementType,
    Order,
    OrderAllocation,
    OrderItem,
)
from app.services.inventory import apply_movement


@dataclass(frozen=True)
class Need:
    """Dòng đơn `order_item_id` cần `quantity` cành loại `flower_type_id`."""

    order_item_id: int
    flower_type_id: int
    quantity: int


def sellable_filter(deliver_by: datetime):
    """Lô bán được cho đơn giao xong trước `deliver_by`: đang hoạt động, còn hàng,
    chưa bị đánh giá héo hẳn, và còn hạn tới lúc giao xong."""
    return (
        Batch.status == BatchStatus.ACTIVE,
        Batch.quantity_available > 0,
        Batch.expected_expiry_at > deliver_by,
        or_(Batch.freshness_override.is_(None), Batch.freshness_override > 0),
    )


async def _lock_sellable_batches(
    session: AsyncSession, flower_ids: Sequence[int], deliver_by: datetime
) -> dict[int, list[Batch]]:
    """Khóa theo thứ tự cố định (loại hoa, hạn dùng, id) — đây cũng chính là thứ tự FEFO."""
    batches = (
        await session.scalars(
            select(Batch)
            .where(Batch.flower_type_id.in_(flower_ids), *sellable_filter(deliver_by))
            .order_by(Batch.flower_type_id, Batch.expected_expiry_at, Batch.id)
            .with_for_update(of=Batch)
            .execution_options(populate_existing=True)
        )
    ).all()
    grouped: dict[int, list[Batch]] = defaultdict(list)
    for b in batches:
        grouped[b.flower_type_id].append(b)
    return grouped


async def _raise_if_short(
    session: AsyncSession, demand: dict[int, int], grouped: dict[int, list[Batch]]
) -> None:
    shortages = {
        fid: (need, sum(b.quantity_available for b in grouped.get(fid, [])))
        for fid, need in demand.items()
    }
    shortages = {fid: v for fid, v in shortages.items() if v[1] < v[0]}
    if not shortages:
        return
    names = dict(
        (
            await session.execute(
                select(FlowerType.id, FlowerType.name).where(FlowerType.id.in_(shortages))
            )
        ).all()
    )
    raise ConflictError(
        "Not enough fresh flowers for this order",
        code="OUT_OF_STOCK",
        extra={
            "shortages": [
                {"flower_type_id": fid, "name": names.get(fid), "needed": need, "available": have}
                for fid, (need, have) in sorted(shortages.items())
            ]
        },
    )


async def allocate_and_reserve(
    session: AsyncSession,
    *,
    order_id: int,
    order_code: str,
    needs: Sequence[Need],
    deliver_by: datetime,
) -> None:
    """Phân bổ FEFO cho cả đơn và trừ kho (RESERVE). All-or-nothing: thiếu một loại hoa là
    ném OUT_OF_STOCK trước khi ghi bất cứ thứ gì. KHÔNG commit."""
    demand: dict[int, int] = defaultdict(int)
    for n in needs:
        demand[n.flower_type_id] += n.quantity

    grouped = await _lock_sellable_batches(session, sorted(demand), deliver_by)
    await _raise_if_short(session, demand, grouped)

    queues = {fid: deque(batches) for fid, batches in grouped.items()}
    remaining = {b.id: b.quantity_available for bs in grouped.values() for b in bs}
    batch_by_id = {b.id: b for bs in grouped.values() for b in bs}
    taken: dict[int, int] = defaultdict(int)

    for n in needs:
        need = n.quantity
        queue = queues[n.flower_type_id]
        while need:
            batch = queue[0]
            take = min(need, remaining[batch.id])
            session.add(
                OrderAllocation(
                    order_item_id=n.order_item_id,
                    batch_id=batch.id,
                    flower_type_id=n.flower_type_id,
                    quantity=take,
                )
            )
            remaining[batch.id] -= take
            taken[batch.id] += take
            need -= take
            if remaining[batch.id] == 0:
                queue.popleft()

    for batch_id, qty in sorted(taken.items()):
        await apply_movement(
            session,
            batch_by_id[batch_id],
            MovementType.RESERVE,
            -qty,
            reason=f"Order {order_code}",
            order_id=order_id,
        )


async def _allocations(session: AsyncSession, order_id: int) -> list[OrderAllocation]:
    return list(
        (
            await session.scalars(
                select(OrderAllocation)
                .join(OrderItem, OrderItem.id == OrderAllocation.order_item_id)
                .where(OrderItem.order_id == order_id)
                .order_by(OrderAllocation.id)
            )
        ).all()
    )


async def release_holdings(session: AsyncSession, order: Order) -> None:
    """Trả hoa về đúng các lô đã lấy (RELEASE) và nhả 1 chỗ của khung giờ.
    Caller đã khóa dòng đơn. KHÔNG commit, KHÔNG đổi trạng thái đơn."""
    slot_day = await session.scalar(
        select(DeliverySlotDay)
        .where(DeliverySlotDay.id == order.delivery_slot_day_id)
        .with_for_update(of=DeliverySlotDay)
        .execution_options(populate_existing=True)
    )
    if slot_day is not None and slot_day.reserved_count > 0:
        slot_day.reserved_count -= 1

    per_batch: dict[int, int] = defaultdict(int)
    for a in await _allocations(session, order.id):
        per_batch[a.batch_id] += a.quantity
    if not per_batch:
        return
    batches = (
        await session.scalars(
            select(Batch)
            .where(Batch.id.in_(per_batch))
            .order_by(Batch.flower_type_id, Batch.expected_expiry_at, Batch.id)
            .with_for_update(of=Batch)
            .execution_options(populate_existing=True)
        )
    ).all()
    for batch in batches:
        await apply_movement(
            session,
            batch,
            MovementType.RELEASE,
            per_batch[batch.id],
            reason=f"Release order {order.code}",
            order_id=order.id,
        )


async def reserve_again(session: AsyncSession, order: Order, now: datetime) -> None:
    """Giữ lại hoa + khung giờ cho đơn đã bị nhả (thanh toán về trễ). Phân bổ FEFO mới
    theo đúng số cành của lần phân bổ cũ. Ném AppError nếu không còn đủ. KHÔNG commit."""
    if order.delivery_starts_at <= now:
        raise AppError("Delivery time has already passed", code="SLOT_TOO_LATE")
    slot_day = await session.scalar(
        select(DeliverySlotDay)
        .where(DeliverySlotDay.id == order.delivery_slot_day_id)
        .with_for_update(of=DeliverySlotDay)
        .execution_options(populate_existing=True)
    )
    if slot_day is None or slot_day.is_closed:
        raise AppError("Delivery slot is closed", code="SLOT_CLOSED")
    if slot_day.reserved_count >= slot_day.capacity:
        raise ConflictError("Delivery slot is full", code="SLOT_FULL")
    slot_day.reserved_count += 1

    old = await _allocations(session, order.id)
    needs_map: dict[tuple[int, int], int] = defaultdict(int)
    for a in old:
        needs_map[(a.order_item_id, a.flower_type_id)] += a.quantity
    await session.execute(
        delete(OrderAllocation).where(OrderAllocation.id.in_([a.id for a in old]))
    )
    await allocate_and_reserve(
        session,
        order_id=order.id,
        order_code=order.code,
        needs=[Need(item_id, fid, qty) for (item_id, fid), qty in sorted(needs_map.items())],
        deliver_by=order.delivery_ends_at,
    )

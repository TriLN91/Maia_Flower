"""Tồn kho theo lô.

Quy tắc vàng: mọi thay đổi `Batch.quantity_available` PHẢI đi qua `apply_movement()`,
để sổ kho luôn khớp với tồn kho (xem bất biến trong models/inventory.py).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.models import (
    Batch,
    BatchStatus,
    FlowerType,
    InventoryMovement,
    MovementType,
    StaffRole,
    StaffUser,
    Supplier,
)
from app.schemas.inventory import BatchCreate, BatchUpdate

# Lô ở các trạng thái này không còn tham gia bán hàng
CLOSED_STATUSES = (BatchStatus.DISCARDED,)
# Nhập lùi ngày tối đa (để nhập bù lô quên ghi)
MAX_BACKDATE = timedelta(days=30)


def utcnow() -> datetime:
    return datetime.now(UTC)


# =====================================================================
# Độ tươi (hàm thuần, không đụng DB -> dễ test)
# =====================================================================
@dataclass(frozen=True)
class FreshnessInfo:
    freshness: float  # 1.0 = vừa nhập, 0.0 = hết hạn
    days_left: float  # âm nếu đã quá hạn
    is_sellable: bool


def compute_freshness(
    *,
    received_at: datetime,
    expected_expiry_at: datetime,
    now: datetime,
    override: float | None = None,
    status: BatchStatus = BatchStatus.ACTIVE,
    quantity_available: int = 1,
) -> FreshnessInfo:
    total = (expected_expiry_at - received_at).total_seconds()
    elapsed = (now - received_at).total_seconds()
    by_time = min(1.0, max(0.0, 1 - elapsed / total))
    # Thợ chỉ được HẠ độ tươi (hoa xuống nhanh hơn dự kiến), không làm hoa "tươi lại"
    freshness = by_time if override is None else min(by_time, override)
    days_left = (expected_expiry_at - now).total_seconds() / 86400
    is_sellable = (
        status == BatchStatus.ACTIVE
        and quantity_available > 0
        and freshness > 0
        and now < expected_expiry_at
    )
    return FreshnessInfo(round(freshness, 4), round(days_left, 2), is_sellable)


def batch_freshness(batch: Batch, now: datetime) -> FreshnessInfo:
    return compute_freshness(
        received_at=batch.received_at,
        expected_expiry_at=batch.expected_expiry_at,
        now=now,
        override=batch.freshness_override,
        status=batch.status,
        quantity_available=batch.quantity_available,
    )


# =====================================================================
# Sổ kho
# =====================================================================
async def apply_movement(
    session: AsyncSession,
    batch: Batch,
    type_: MovementType,
    quantity: int,
    *,
    reason: str | None = None,
    actor: StaffUser | None = None,
    order_id: int | None = None,
) -> InventoryMovement:
    """Ghi một dòng sổ kho và cập nhật tồn của lô. KHÔNG commit — caller quyết định transaction.

    Caller phải đã khóa dòng lô (`lock_batch` / SELECT … FOR UPDATE) trước khi gọi.
    """
    if quantity == 0:
        raise ValueError("Movement quantity must be non-zero")
    new_available = batch.quantity_available + quantity
    if new_available < 0:
        raise AppError(
            "Not enough stems in this batch",
            code="INSUFFICIENT_STOCK",
            extra={"batch_id": batch.id, "available": batch.quantity_available},
        )

    batch.quantity_available = new_available
    if new_available == 0 and batch.status == BatchStatus.ACTIVE:
        batch.status = BatchStatus.DEPLETED
    elif new_available > 0 and batch.status == BatchStatus.DEPLETED:
        batch.status = BatchStatus.ACTIVE  # vd. nhả giữ chỗ trả hoa về lô

    movement = InventoryMovement(
        batch_id=batch.id,
        type=type_,
        quantity=quantity,
        reason=reason,
        order_id=order_id,
        created_by_id=actor.id if actor else None,
    )
    session.add(movement)
    return movement


async def get_batch(session: AsyncSession, batch_id: int) -> Batch:
    # populate_existing: nạp lại cả quan hệ (loại hoa, NCC) kể cả khi object đã có trong session
    # — với async không được để quan hệ tự lazy-load lúc serialize.
    batch = await session.scalar(
        select(Batch).where(Batch.id == batch_id).execution_options(populate_existing=True)
    )
    if batch is None:
        raise NotFoundError("Batch not found")
    return batch


async def lock_batch(session: AsyncSession, batch_id: int) -> Batch:
    """Đọc lô kèm khóa dòng: hai thao tác cùng lúc trên một lô sẽ chạy lần lượt."""
    batch = await session.scalar(
        select(Batch)
        .where(Batch.id == batch_id)
        .with_for_update(of=Batch)
        .execution_options(populate_existing=True)
    )
    if batch is None:
        raise NotFoundError("Batch not found")
    return batch


# =====================================================================
# Nghiệp vụ
# =====================================================================
async def create_batch(session: AsyncSession, actor: StaffUser, data: BatchCreate) -> Batch:
    now = utcnow()
    flower = await session.get(FlowerType, data.flower_type_id)
    if flower is None:
        raise NotFoundError("Flower type not found")
    if not flower.is_active:
        raise AppError("Flower type is inactive", code="INACTIVE_FLOWER_TYPE")
    supplier = await session.get(Supplier, data.supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found")
    if not supplier.is_active:
        raise AppError("Supplier is inactive", code="INACTIVE_SUPPLIER")

    received_at = data.received_at or now
    if received_at > now + timedelta(minutes=5):  # chừa lệch đồng hồ
        raise AppError("received_at cannot be in the future", code="INVALID_RECEIVED_AT")
    if received_at < now - MAX_BACKDATE:
        raise AppError("received_at is too far in the past", code="INVALID_RECEIVED_AT")

    expiry = data.expected_expiry_at or received_at + timedelta(days=flower.vase_life_days)
    if expiry <= received_at:
        raise AppError("expected_expiry_at must be after received_at", code="INVALID_EXPIRY")

    batch = Batch(
        flower_type_id=flower.id,
        supplier_id=supplier.id,
        quantity_received=data.quantity,
        quantity_available=0,
        cost_per_stem=data.cost_per_stem,
        received_at=received_at,
        expected_expiry_at=expiry,
        note=data.note,
        created_by_id=actor.id,
    )
    session.add(batch)
    await session.flush()  # cần batch.id cho dòng sổ kho
    await apply_movement(session, batch, MovementType.IMPORT, data.quantity, actor=actor)
    await session.commit()
    return await get_batch(session, batch.id)


async def update_batch(
    session: AsyncSession, actor: StaffUser, batch_id: int, data: BatchUpdate
) -> Batch:
    changes = data.model_dump(exclude_unset=True)
    owner_only = set(changes) - {"freshness_override"}
    if owner_only and actor.role != StaffRole.OWNER:
        raise AppError(
            "Only the owner can change these fields",
            code="FORBIDDEN_FIELDS",
            status_code=403,
            extra={"fields": sorted(owner_only)},
        )

    batch = await lock_batch(session, batch_id)
    for field in ("expected_expiry_at", "cost_per_stem"):
        if field in changes and changes[field] is None:
            raise AppError(f"Field '{field}' cannot be null", code="NULL_NOT_ALLOWED")
    if "expected_expiry_at" in changes and changes["expected_expiry_at"] <= batch.received_at:
        raise AppError("expected_expiry_at must be after received_at", code="INVALID_EXPIRY")

    for field, value in changes.items():
        setattr(batch, field, value)
    # Chủ shop gia hạn lô đang chờ xem xét -> cho bán lại
    if (
        batch.status == BatchStatus.NEEDS_REVIEW
        and "expected_expiry_at" in changes
        and batch.expected_expiry_at > utcnow()
    ):
        batch.status = BatchStatus.ACTIVE if batch.quantity_available > 0 else BatchStatus.DEPLETED

    await session.commit()
    session.expire(batch)
    return await get_batch(session, batch_id)


def _ensure_open(batch: Batch) -> None:
    if batch.status in CLOSED_STATUSES:
        raise AppError("Batch is closed", code="BATCH_CLOSED")


async def record_waste(
    session: AsyncSession, actor: StaffUser, batch_id: int, quantity: int, reason: str
) -> Batch:
    batch = await lock_batch(session, batch_id)
    _ensure_open(batch)
    await apply_movement(session, batch, MovementType.WASTE, -quantity, reason=reason, actor=actor)
    await session.commit()
    return await get_batch(session, batch_id)


async def discard_batch(
    session: AsyncSession, actor: StaffUser, batch_id: int, reason: str
) -> Batch:
    """Bỏ toàn bộ phần còn lại của lô (vd. lô quá hạn)."""
    batch = await lock_batch(session, batch_id)
    _ensure_open(batch)
    if batch.quantity_available > 0:
        await apply_movement(
            session,
            batch,
            MovementType.WASTE,
            -batch.quantity_available,
            reason=reason,
            actor=actor,
        )
    batch.status = BatchStatus.DISCARDED
    await session.commit()
    return await get_batch(session, batch_id)


async def adjust_batch(
    session: AsyncSession, actor: StaffUser, batch_id: int, counted: int, reason: str
) -> Batch:
    """Kiểm kê: đặt tồn bằng số đếm thực tế; chênh lệch được ghi thành một dòng ADJUST."""
    batch = await lock_batch(session, batch_id)
    _ensure_open(batch)
    delta = counted - batch.quantity_available
    if delta == 0:
        raise AppError("Counted quantity equals current stock", code="NO_CHANGE")
    await apply_movement(session, batch, MovementType.ADJUST, delta, reason=reason, actor=actor)
    await session.commit()
    return await get_batch(session, batch_id)


async def list_batches(
    session: AsyncSession,
    *,
    flower_type_id: int | None = None,
    status: BatchStatus | None = None,
) -> Sequence[Batch]:
    stmt = select(Batch).order_by(Batch.expected_expiry_at, Batch.id)
    if flower_type_id is not None:
        stmt = stmt.where(Batch.flower_type_id == flower_type_id)
    if status is not None:
        stmt = stmt.where(Batch.status == status)
    return (await session.scalars(stmt)).all()


async def list_movements(session: AsyncSession, batch_id: int) -> Sequence[InventoryMovement]:
    await get_batch(session, batch_id)
    return (
        await session.scalars(
            select(InventoryMovement)
            .where(InventoryMovement.batch_id == batch_id)
            .order_by(InventoryMovement.id)
        )
    ).all()


@dataclass
class _Stock:
    flower: FlowerType
    total_available: int = 0
    sellable: int = 0
    expiring_soon: int = 0
    freshness_weighted: float = 0.0
    nearest_expiry_at: datetime | None = None
    batch_count: int = 0


async def inventory_summary(session: AsyncSession, now: datetime | None = None) -> list[_Stock]:
    now = now or utcnow()
    soon = now + timedelta(days=get_settings().expiring_soon_days)

    flowers = (
        await session.scalars(
            select(FlowerType).where(FlowerType.is_active.is_(True)).order_by(FlowerType.name)
        )
    ).all()
    stock: dict[int, _Stock] = {f.id: _Stock(flower=f) for f in flowers}

    batches = (
        await session.scalars(
            select(Batch).where(
                Batch.status.in_([BatchStatus.ACTIVE, BatchStatus.NEEDS_REVIEW]),
                Batch.quantity_available > 0,
            )
        )
    ).all()

    per_flower: dict[int, list[Batch]] = defaultdict(list)
    for b in batches:
        per_flower[b.flower_type_id].append(b)

    for flower_id, items in per_flower.items():
        s = stock.get(flower_id)
        if s is None:  # loại hoa đã ngừng bán nhưng còn lô cũ — bỏ qua trong tổng hợp
            continue
        for b in items:
            info = batch_freshness(b, now)
            s.batch_count += 1
            s.total_available += b.quantity_available
            if info.is_sellable:
                s.sellable += b.quantity_available
                s.freshness_weighted += info.freshness * b.quantity_available
                if b.expected_expiry_at <= soon:
                    s.expiring_soon += b.quantity_available
                if s.nearest_expiry_at is None or b.expected_expiry_at < s.nearest_expiry_at:
                    s.nearest_expiry_at = b.expected_expiry_at
    return list(stock.values())

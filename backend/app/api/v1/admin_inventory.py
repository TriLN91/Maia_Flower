from collections.abc import Sequence
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.api.deps import CurrentOwner, CurrentStaff, SessionDep
from app.models import Batch, BatchStatus, InventoryMovement
from app.schemas.catalog import FlowerBrief
from app.schemas.inventory import (
    AdjustIn,
    BatchCreate,
    BatchOut,
    BatchUpdate,
    DiscardIn,
    FlowerStock,
    MovementOut,
    TemplateCostOut,
    WasteIn,
)
from app.services import costing, inventory

router = APIRouter(prefix="/admin")


def _batch_out(batch: Batch, now: datetime) -> BatchOut:
    info = inventory.batch_freshness(batch, now)
    return BatchOut.model_validate(
        {
            **{c: getattr(batch, c) for c in BatchOut.model_fields if hasattr(batch, c)},
            "freshness": info.freshness,
            "days_left": info.days_left,
            "is_sellable": info.is_sellable,
        }
    )


# ---------- Lô hàng (thợ bó được nhập lô, ghi hỏng, hạ độ tươi) ----------
@router.post(
    "/batches",
    response_model=BatchOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: inventory"],
)
async def create_batch(session: SessionDep, user: CurrentStaff, body: BatchCreate) -> BatchOut:
    """Nhập một lô hoa. Hạn dùng mặc định = ngày nhận + số ngày tươi của loại hoa."""
    batch = await inventory.create_batch(session, user, body)
    return _batch_out(batch, inventory.utcnow())


@router.get("/batches", response_model=list[BatchOut], tags=["admin: inventory"])
async def list_batches(
    session: SessionDep,
    _: CurrentStaff,
    flower_type_id: int | None = None,
    status: BatchStatus | None = None,
) -> list[BatchOut]:
    """Danh sách lô, sắp theo hạn dùng gần nhất trước (thứ tự FEFO)."""
    now = inventory.utcnow()
    batches = await inventory.list_batches(session, flower_type_id=flower_type_id, status=status)
    return [_batch_out(b, now) for b in batches]


@router.get("/batches/{batch_id}", response_model=BatchOut, tags=["admin: inventory"])
async def get_batch(session: SessionDep, _: CurrentStaff, batch_id: int) -> BatchOut:
    return _batch_out(await inventory.get_batch(session, batch_id), inventory.utcnow())


@router.patch("/batches/{batch_id}", response_model=BatchOut, tags=["admin: inventory"])
async def update_batch(
    session: SessionDep, user: CurrentStaff, batch_id: int, body: BatchUpdate
) -> BatchOut:
    """Thợ bó: chỉ `freshness_override`. Chủ shop: thêm hạn dùng, giá nhập, ghi chú."""
    batch = await inventory.update_batch(session, user, batch_id, body)
    return _batch_out(batch, inventory.utcnow())


@router.post("/batches/{batch_id}/waste", response_model=BatchOut, tags=["admin: inventory"])
async def record_waste(
    session: SessionDep, user: CurrentStaff, batch_id: int, body: WasteIn
) -> BatchOut:
    batch = await inventory.record_waste(session, user, batch_id, body.quantity, body.reason)
    return _batch_out(batch, inventory.utcnow())


@router.post("/batches/{batch_id}/discard", response_model=BatchOut, tags=["admin: inventory"])
async def discard_batch(
    session: SessionDep, owner: CurrentOwner, batch_id: int, body: DiscardIn
) -> BatchOut:
    """Bỏ toàn bộ phần còn lại của lô (ghi hao hụt) và đóng lô."""
    batch = await inventory.discard_batch(session, owner, batch_id, body.reason)
    return _batch_out(batch, inventory.utcnow())


@router.post("/batches/{batch_id}/adjust", response_model=BatchOut, tags=["admin: inventory"])
async def adjust_batch(
    session: SessionDep, owner: CurrentOwner, batch_id: int, body: AdjustIn
) -> BatchOut:
    """Kiểm kê: đặt tồn theo số đếm thực tế."""
    batch = await inventory.adjust_batch(
        session, owner, batch_id, body.counted_quantity, body.reason
    )
    return _batch_out(batch, inventory.utcnow())


@router.get(
    "/batches/{batch_id}/movements", response_model=list[MovementOut], tags=["admin: inventory"]
)
async def list_movements(
    session: SessionDep, _: CurrentStaff, batch_id: int
) -> Sequence[InventoryMovement]:
    return await inventory.list_movements(session, batch_id)


# ---------- Tổng hợp ----------
@router.get("/inventory", response_model=list[FlowerStock], tags=["admin: inventory"])
async def inventory_summary(session: SessionDep, _: CurrentStaff) -> list[FlowerStock]:
    """Tồn kho theo loại hoa: tổng, bán được, sắp hết hạn, độ tươi trung bình."""
    rows = await inventory.inventory_summary(session)
    return [
        FlowerStock(
            flower_type=FlowerBrief.model_validate(s.flower),
            total_available=s.total_available,
            sellable=s.sellable,
            expiring_soon=s.expiring_soon,
            avg_freshness=round(s.freshness_weighted / s.sellable, 4) if s.sellable else None,
            nearest_expiry_at=s.nearest_expiry_at,
            batch_count=s.batch_count,
        )
        for s in rows
    ]


class LedgerAuditOut(BaseModel):
    batches_checked: int
    ok: bool
    mismatches: list[dict]


@router.get("/inventory/audit", response_model=LedgerAuditOut, tags=["admin: inventory"])
async def ledger_audit(session: SessionDep, _: CurrentOwner) -> LedgerAuditOut:
    """Kiểm tra bất biến tồn kho = tổng sổ kho trên mọi lô (dùng sau khi seed / sự cố)."""
    checked, mismatches = await inventory.ledger_audit(session)
    return LedgerAuditOut(
        batches_checked=checked, ok=not mismatches, mismatches=[m.__dict__ for m in mismatches]
    )


@router.get(
    "/templates/{template_id}/cost", response_model=TemplateCostOut, tags=["admin: templates"]
)
async def template_cost(session: SessionDep, _: CurrentOwner, template_id: int) -> TemplateCostOut:
    """Giá vốn hiện tại của mẫu (từ giá nhập các lô còn hàng) và cảnh báo biên lợi nhuận."""
    return await costing.template_cost(session, template_id)

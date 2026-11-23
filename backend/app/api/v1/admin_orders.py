from fastapi import APIRouter

from app.api.deps import CurrentStaff, SessionDep
from app.models import Order
from app.schemas.orders import OrderAdminOut
from app.services import checkout

router = APIRouter(prefix="/admin/orders", tags=["admin: orders"])


@router.get("/{order_id}", response_model=OrderAdminOut)
async def get_order(session: SessionDep, _: CurrentStaff, order_id: int) -> Order:
    """Chi tiết đơn kèm phân bổ: thợ bó biết lấy bao nhiêu cành từ lô nào."""
    return await checkout.get_order(session, order_id)

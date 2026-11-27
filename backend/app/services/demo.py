"""Chế độ demo công khai (DEMO_MODE=true): giữ cho bản demo luôn có hoa để khách đặt thử.

Mỗi sáng tự nhập hàng theo đúng gợi ý nhập hàng của hệ thống (ngày 9) — chính tính năng
"gợi ý nhập" được dùng để vận hành bản demo.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Supplier
from app.schemas.inventory import BatchCreate
from app.services.forecasting import local_today, restock_suggestions
from app.services.inventory import create_batch

log = logging.getLogger(__name__)


async def auto_restock(session: AsyncSession, now: datetime) -> int:
    """Nhập các lô theo gợi ý cho hôm nay. Trả về số lô đã nhập."""
    supplier_id = await session.scalar(
        select(Supplier.id).where(Supplier.is_active.is_(True)).order_by(Supplier.id)
    )
    if supplier_id is None:
        return 0
    lines = await restock_suggestions(session, now, local_today(now))
    created = 0
    for line in lines:
        if line.suggested_qty <= 0:
            continue
        await create_batch(
            session,
            None,  # hệ thống nhập, không phải nhân viên
            BatchCreate(
                flower_type_id=line.flower_type_id,
                supplier_id=supplier_id,
                quantity=line.suggested_qty,
                cost_per_stem=line.est_unit_cost,
                note="Tự nhập theo gợi ý (chế độ demo)",
            ),
        )
        created += 1
    log.info("Demo auto-restock: %d batches", created)
    return created

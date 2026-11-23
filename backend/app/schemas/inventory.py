from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.inventory import BatchStatus, MovementType
from app.schemas.catalog import FlowerBrief
from app.schemas.common import Money

Reason = Annotated[str, Field(min_length=1, max_length=500)]
Freshness = Annotated[float, Field(ge=0, le=1)]


class BatchCreate(BaseModel):
    flower_type_id: int
    supplier_id: int
    quantity: Annotated[int, Field(ge=1, le=100_000, description="Số cành nhận")]
    cost_per_stem: Money
    received_at: AwareDatetime | None = Field(
        default=None, description="Mặc định là bây giờ. Không được ở tương lai."
    )
    expected_expiry_at: AwareDatetime | None = Field(
        default=None, description="Mặc định = received_at + số ngày tươi của loại hoa"
    )
    note: Annotated[str, Field(max_length=500)] | None = None


class BatchUpdate(BaseModel):
    """Thợ bó chỉ được sửa `freshness_override`; các trường khác cần quyền chủ shop."""

    freshness_override: Freshness | None = None
    expected_expiry_at: AwareDatetime | None = None
    cost_per_stem: Money | None = None
    note: Annotated[str, Field(max_length=500)] | None = None


class WasteIn(BaseModel):
    quantity: Annotated[int, Field(ge=1)]
    reason: Reason


class DiscardIn(BaseModel):
    reason: Reason


class AdjustIn(BaseModel):
    counted_quantity: Annotated[int, Field(ge=0, description="Số cành đếm được thực tế")]
    reason: Reason


class SupplierBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    flower_type: FlowerBrief
    supplier: SupplierBrief
    quantity_received: int
    quantity_available: int
    cost_per_stem: int
    received_at: datetime
    expected_expiry_at: datetime
    freshness_override: float | None
    status: BatchStatus
    note: str | None
    # Tính tại thời điểm trả về
    freshness: float
    days_left: float
    is_sellable: bool


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: MovementType
    quantity: int
    reason: str | None
    order_id: int | None
    created_by_id: int | None
    created_at: datetime


class FlowerStock(BaseModel):
    flower_type: FlowerBrief
    total_available: int = Field(description="Tổng số cành còn trong các lô đang hoạt động")
    sellable: int = Field(description="Số cành còn tươi, bán được ngay")
    expiring_soon: int = Field(description="Số cành bán được nhưng hết hạn trong N ngày tới")
    avg_freshness: float | None = Field(description="Độ tươi trung bình theo số cành")
    nearest_expiry_at: datetime | None
    batch_count: int


class CostLine(BaseModel):
    flower_type: FlowerBrief
    quantity: int
    unit_cost: int
    line_cost: int
    cost_source: str = Field(
        description="'batches' = TB các lô còn hàng, 'reference' = giá tham khảo"
    )


class TemplateCostOut(BaseModel):
    template_id: int
    price: int
    cost: int
    margin_pct: float | None = Field(description="(giá − vốn) / vốn × 100")
    max_discount_pct: int
    lowest_price_after_discount: int
    min_margin_pct: int
    price_floor: int = Field(description="Giá thấp nhất cho phép = vốn × (1 + biên tối thiểu)")
    warnings: list[str]
    lines: list[CostLine]

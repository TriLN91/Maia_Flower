# Import mọi model ở đây để Alembic (autogenerate) và Base.metadata thấy đủ bảng.
from app.models.base import Base
from app.models.catalog import (
    BouquetTemplate,
    FlowerType,
    Supplier,
    TemplateItem,
    TemplatePriceHistory,
)
from app.models.inventory import Batch, BatchStatus, InventoryMovement, MovementType
from app.models.staff_user import StaffRole, StaffUser

__all__ = [
    "Base",
    "Batch",
    "BatchStatus",
    "BouquetTemplate",
    "FlowerType",
    "InventoryMovement",
    "MovementType",
    "StaffRole",
    "StaffUser",
    "Supplier",
    "TemplateItem",
    "TemplatePriceHistory",
]

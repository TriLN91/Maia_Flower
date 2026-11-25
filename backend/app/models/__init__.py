# Import mọi model ở đây để Alembic (autogenerate) và Base.metadata thấy đủ bảng.
from app.models.base import Base
from app.models.catalog import (
    BouquetTemplate,
    FlowerType,
    Supplier,
    TemplateItem,
    TemplatePriceHistory,
)
from app.models.delivery import DeliverySlot, DeliverySlotDay
from app.models.inventory import Batch, BatchStatus, InventoryMovement, MovementType
from app.models.orders import (
    Order,
    OrderAllocation,
    OrderEvent,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from app.models.pricing import TemplateDiscount, TemplateDiscountLog, UrgencyScore
from app.models.settings import ShopSetting
from app.models.staff_user import StaffRole, StaffUser

__all__ = [
    "Base",
    "Batch",
    "BatchStatus",
    "BouquetTemplate",
    "DeliverySlot",
    "DeliverySlotDay",
    "FlowerType",
    "InventoryMovement",
    "MovementType",
    "Order",
    "OrderAllocation",
    "OrderEvent",
    "OrderItem",
    "OrderStatus",
    "Payment",
    "PaymentStatus",
    "ShopSetting",
    "StaffRole",
    "StaffUser",
    "Supplier",
    "TemplateItem",
    "TemplateDiscount",
    "TemplateDiscountLog",
    "TemplatePriceHistory",
    "UrgencyScore",
]

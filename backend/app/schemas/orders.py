import re
from datetime import date, datetime, time
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.models.orders import OrderStatus, PaymentStatus
from app.schemas.common import Name


def normalize_vn_phone(value: str) -> str:
    """'0909 123 456' / '+84 909-123-456' / '84909123456' -> '0909123456'."""
    digits = re.sub(r"[\s.\-()]", "", value)
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    if not re.fullmatch(r"0[35789]\d{8}", digits):
        raise ValueError("Invalid Vietnamese mobile number")
    return digits


VNPhone = Annotated[str, Field(max_length=20), AfterValidator(normalize_vn_phone)]


# ---------- Giỏ hàng ----------
class CartLineIn(BaseModel):
    template_id: int
    quantity: Annotated[int, Field(ge=1, le=20)]


Cart = Annotated[list[CartLineIn], Field(min_length=1, max_length=10)]


def _no_duplicate_templates(lines: list[CartLineIn]) -> list[CartLineIn]:
    ids = [line.template_id for line in lines]
    if len(ids) != len(set(ids)):
        raise ValueError("Each template may appear only once; increase quantity instead")
    return lines


class CartQuoteIn(BaseModel):
    items: Cart
    delivery_quote_token: str | None = Field(
        default=None, description="Token từ /shop/delivery/quote — có thì tính luôn phí ship"
    )
    delivery_date: date | None = Field(default=None, description="Để tính phụ phí ngày lễ")

    _check = field_validator("items")(_no_duplicate_templates)


class QuoteLineOut(BaseModel):
    template_id: int
    name: str
    quantity: int
    unit_price: int
    discount_pct: int
    line_total: int
    available: bool = Field(description="Hiện còn đủ hoa cho dòng này (không giữ chỗ)")


class CartQuoteOut(BaseModel):
    lines: list[QuoteLineOut]
    subtotal: int
    discount_total: int
    delivery_fee: int | None = Field(description="null nếu chưa có địa chỉ (chưa có quote token)")
    total: int
    all_available: bool


# ---------- Khung giờ ----------
class SlotAvailabilityOut(BaseModel):
    slot_id: int
    date: date
    start_time: time
    end_time: time
    capacity: int
    remaining: int
    bookable: bool
    reason: str | None = Field(
        description="Lý do không đặt được: FULL, CLOSED, TOO_LATE, OUT_OF_WINDOW"
    )


# ---------- Đặt hàng ----------
class OrderCreate(BaseModel):
    items: Cart
    customer_name: Name
    customer_phone: VNPhone
    recipient_name: Name | None = None
    recipient_phone: VNPhone | None = None
    delivery_address: Annotated[str, Field(min_length=5, max_length=500)]
    delivery_quote_token: str = Field(
        description="Token từ /shop/delivery/quote: chứa tọa độ + quãng đường đã được server ký"
    )
    delivery_date: date
    slot_id: int
    card_message: Annotated[str, Field(max_length=300)] | None = None
    note: Annotated[str, Field(max_length=500)] | None = None

    _check = field_validator("items")(_no_duplicate_templates)


class OrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    template_id: int
    template_name: str
    quantity: int
    unit_price: int
    discount_pct: int
    line_total: int


class TimelineEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    to_status: OrderStatus
    created_at: datetime


class EventOut(TimelineEntry):
    from_status: OrderStatus | None
    actor: str
    actor_id: int | None
    note: str | None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    txn_ref: str
    provider: str
    amount: int
    status: PaymentStatus
    response_code: str | None
    needs_refund: bool
    paid_at: datetime | None
    created_at: datetime


class OrderPublicOut(BaseModel):
    """Khách xem đơn của mình. Không lộ lô hàng, giá vốn; số điện thoại bị che bớt."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    status: OrderStatus
    customer_name: str
    customer_phone_masked: str
    recipient_name: str | None
    delivery_address: str
    delivery_starts_at: datetime
    delivery_ends_at: datetime
    card_message: str | None
    items: list[OrderLineOut]
    subtotal: int
    discount_total: int
    delivery_fee: int
    total: int
    hold_expires_at: datetime | None
    created_at: datetime
    timeline: list[TimelineEntry] = Field(validation_alias="events")


class OrderCreatedOut(OrderPublicOut):
    tracking_token: str = Field(description="Chỉ trả về lúc tạo đơn; dùng cho link theo dõi")


class AllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    flower_type_id: int
    quantity: int


class OrderItemAdminOut(OrderLineOut):
    allocations: list[AllocationOut]


class OrderAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    status: OrderStatus
    customer_name: str
    customer_phone: str
    recipient_name: str | None
    recipient_phone: str | None
    delivery_address: str
    delivery_lat: float | None
    delivery_lng: float | None
    delivery_distance_km: float | None
    delivery_starts_at: datetime
    delivery_ends_at: datetime
    card_message: str | None
    note: str | None
    items: list[OrderItemAdminOut]
    subtotal: int
    discount_total: int
    delivery_fee: int
    total: int
    hold_expires_at: datetime | None
    created_at: datetime
    events: list[EventOut]
    payments: list[PaymentOut]


class OrderSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    status: OrderStatus
    customer_name: str
    delivery_starts_at: datetime
    delivery_ends_at: datetime
    total: int
    item_count: int
    created_at: datetime


class TransitionIn(BaseModel):
    to_status: OrderStatus
    note: Annotated[str, Field(max_length=500)] | None = None

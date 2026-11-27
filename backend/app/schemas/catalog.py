from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ImageUrl, Money, Name, PositiveMoney

Slug = Annotated[str, Field(min_length=1, max_length=140, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
Phone = Annotated[str, Field(pattern=r"^\+?[0-9 .-]{8,20}$")]


# ---------- Loại hoa ----------
class FlowerTypeCreate(BaseModel):
    name: Name
    color: Annotated[str, Field(min_length=1, max_length=40)]
    reference_cost: Money = 0
    vase_life_days: Annotated[int, Field(ge=1, le=60)]
    image_url: ImageUrl | None = None


class FlowerTypeUpdate(BaseModel):
    name: Name | None = None
    color: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    reference_cost: Money | None = None
    vase_life_days: Annotated[int, Field(ge=1, le=60)] | None = None
    image_url: ImageUrl | None = None
    is_active: bool | None = None


class FlowerTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    reference_cost: int
    vase_life_days: int
    image_url: str | None
    is_active: bool


# ---------- Nhà cung cấp ----------
class SupplierCreate(BaseModel):
    name: Name
    phone: Phone | None = None
    note: Annotated[str, Field(max_length=2000)] | None = None


class SupplierUpdate(BaseModel):
    name: Name | None = None
    phone: Phone | None = None
    note: Annotated[str, Field(max_length=2000)] | None = None
    is_active: bool | None = None


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    note: str | None
    is_active: bool


# ---------- Mẫu bó hoa ----------
class TemplateItemIn(BaseModel):
    flower_type_id: int
    quantity: Annotated[int, Field(ge=1, le=500)]


Recipe = Annotated[list[TemplateItemIn], Field(min_length=1, max_length=30)]


def _no_duplicate_flowers(items: list[TemplateItemIn]) -> list[TemplateItemIn]:
    ids = [i.flower_type_id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Each flower type may appear only once in a recipe")
    return items


class TemplateCreate(BaseModel):
    name: Name
    slug: Slug | None = Field(default=None, description="Bỏ trống để tự sinh từ tên")
    description: Annotated[str, Field(max_length=5000)] = ""
    image_url: ImageUrl | None = None
    price: PositiveMoney
    discount_locked: bool = False
    items: Recipe

    _check_items = field_validator("items")(_no_duplicate_flowers)


class TemplateUpdate(BaseModel):
    name: Name | None = None
    slug: Slug | None = None
    description: Annotated[str, Field(max_length=5000)] | None = None
    image_url: ImageUrl | None = None
    price: PositiveMoney | None = None
    discount_locked: bool | None = None
    is_active: bool | None = None


class RecipeReplace(BaseModel):
    items: Recipe

    _check_items = field_validator("items")(_no_duplicate_flowers)


class FlowerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str


class TemplateItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    flower_type: FlowerBrief
    quantity: int


class TemplateAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str
    image_url: str | None
    price: int
    discount_locked: bool
    is_active: bool
    items: list[TemplateItemOut]
    updated_by_id: int | None
    created_at: datetime
    updated_at: datetime
    current_discount_pct: int = 0


class TemplatePublicOut(BaseModel):
    """Dữ liệu khách được xem — không lộ giá vốn, trạng thái nội bộ."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str
    image_url: str | None
    price: int
    items: list[TemplateItemOut]
    discount_pct: int = 0
    final_price: int | None = None  # = price × (100 − discount_pct) / 100

    def with_discount(self, pct: int) -> "TemplatePublicOut":
        return self.model_copy(
            update={"discount_pct": pct, "final_price": self.price * (100 - pct) // 100}
        )


class PriceHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_price: int
    new_price: int
    changed_by_id: int | None
    changed_at: datetime

from collections.abc import Sequence

from fastapi import APIRouter, status

from app.api.deps import CurrentOwner, CurrentStaff, SessionDep
from app.models import BouquetTemplate, FlowerType, Supplier, TemplatePriceHistory
from app.schemas.catalog import (
    FlowerTypeCreate,
    FlowerTypeOut,
    FlowerTypeUpdate,
    PriceHistoryOut,
    RecipeReplace,
    SupplierCreate,
    SupplierOut,
    SupplierUpdate,
    TemplateAdminOut,
    TemplateCreate,
    TemplateUpdate,
)
from app.services import catalog, pricing

# Thợ bó xem được danh mục (để biết công thức khi bó); chỉ chủ shop được sửa.
router = APIRouter(prefix="/admin")


# ---------- Loại hoa ----------
@router.get("/flower-types", response_model=list[FlowerTypeOut], tags=["admin: flower types"])
async def list_flower_types(session: SessionDep, _: CurrentStaff) -> Sequence[FlowerType]:
    return await catalog.list_flower_types(session)


@router.post(
    "/flower-types",
    response_model=FlowerTypeOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: flower types"],
)
async def create_flower_type(
    session: SessionDep, _: CurrentOwner, body: FlowerTypeCreate
) -> FlowerType:
    return await catalog.create_flower_type(session, body)


@router.patch(
    "/flower-types/{flower_type_id}", response_model=FlowerTypeOut, tags=["admin: flower types"]
)
async def update_flower_type(
    session: SessionDep, _: CurrentOwner, flower_type_id: int, body: FlowerTypeUpdate
) -> FlowerType:
    return await catalog.update_flower_type(session, flower_type_id, body)


# ---------- Nhà cung cấp ----------
@router.get("/suppliers", response_model=list[SupplierOut], tags=["admin: suppliers"])
async def list_suppliers(session: SessionDep, _: CurrentStaff) -> Sequence[Supplier]:
    return await catalog.list_suppliers(session)


@router.post(
    "/suppliers",
    response_model=SupplierOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: suppliers"],
)
async def create_supplier(session: SessionDep, _: CurrentOwner, body: SupplierCreate) -> Supplier:
    return await catalog.create_supplier(session, body)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut, tags=["admin: suppliers"])
async def update_supplier(
    session: SessionDep, _: CurrentOwner, supplier_id: int, body: SupplierUpdate
) -> Supplier:
    return await catalog.update_supplier(session, supplier_id, body)


# ---------- Mẫu bó hoa ----------
@router.get("/templates", response_model=list[TemplateAdminOut], tags=["admin: templates"])
async def list_templates(session: SessionDep, _: CurrentStaff) -> list[TemplateAdminOut]:
    """Kèm `current_discount_pct` — mức giảm động đang áp dụng."""
    rows = await catalog.list_templates_admin(session)
    discounts = await pricing.current_discounts(session, [t.id for t in rows])
    return [
        TemplateAdminOut.model_validate(t).model_copy(
            update={"current_discount_pct": discounts.get(t.id, 0)}
        )
        for t in rows
    ]


@router.post(
    "/templates",
    response_model=TemplateAdminOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: templates"],
)
async def create_template(
    session: SessionDep, owner: CurrentOwner, body: TemplateCreate
) -> BouquetTemplate:
    return await catalog.create_template(session, owner, body)


@router.get("/templates/{template_id}", response_model=TemplateAdminOut, tags=["admin: templates"])
async def get_template(session: SessionDep, _: CurrentStaff, template_id: int) -> BouquetTemplate:
    return await catalog.get_template(session, template_id)


@router.patch(
    "/templates/{template_id}", response_model=TemplateAdminOut, tags=["admin: templates"]
)
async def update_template(
    session: SessionDep, owner: CurrentOwner, template_id: int, body: TemplateUpdate
) -> BouquetTemplate:
    """Sửa thông tin/giá/trạng thái. Đổi giá sẽ tự ghi vào lịch sử giá."""
    return await catalog.update_template(session, owner, template_id, body)


@router.put(
    "/templates/{template_id}/items", response_model=TemplateAdminOut, tags=["admin: templates"]
)
async def replace_recipe(
    session: SessionDep, owner: CurrentOwner, template_id: int, body: RecipeReplace
) -> BouquetTemplate:
    """Thay toàn bộ công thức của mẫu."""
    return await catalog.replace_recipe(session, owner, template_id, body.items)


@router.get(
    "/templates/{template_id}/price-history",
    response_model=list[PriceHistoryOut],
    tags=["admin: templates"],
)
async def price_history(
    session: SessionDep, _: CurrentOwner, template_id: int
) -> Sequence[TemplatePriceHistory]:
    return await catalog.price_history(session, template_id)

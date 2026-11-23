from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.text import slugify
from app.models import (
    BouquetTemplate,
    FlowerType,
    StaffUser,
    Supplier,
    TemplateItem,
    TemplatePriceHistory,
)
from app.schemas.catalog import (
    FlowerTypeCreate,
    FlowerTypeUpdate,
    SupplierCreate,
    SupplierUpdate,
    TemplateCreate,
    TemplateItemIn,
    TemplateUpdate,
)


def _apply_patch(obj: Any, changes: dict[str, Any], nullable: set[str]) -> None:
    """Gán các trường PATCH; chặn gửi null cho trường bắt buộc."""
    for field, value in changes.items():
        if value is None and field not in nullable:
            raise AppError(f"Field '{field}' cannot be null", code="NULL_NOT_ALLOWED")
        setattr(obj, field, value)


async def _commit_unique(session: AsyncSession, what: str) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(f"{what} already exists", code="DUPLICATE") from None


# =====================================================================
# Loại hoa
# =====================================================================
async def list_flower_types(
    session: AsyncSession, *, include_inactive: bool = True
) -> Sequence[FlowerType]:
    stmt = select(FlowerType).order_by(FlowerType.name)
    if not include_inactive:
        stmt = stmt.where(FlowerType.is_active.is_(True))
    return (await session.scalars(stmt)).all()


async def get_flower_type(session: AsyncSession, flower_type_id: int) -> FlowerType:
    flower = await session.get(FlowerType, flower_type_id)
    if flower is None:
        raise NotFoundError("Flower type not found")
    return flower


async def create_flower_type(session: AsyncSession, data: FlowerTypeCreate) -> FlowerType:
    flower = FlowerType(**data.model_dump())
    session.add(flower)
    await _commit_unique(session, "Flower type with this name")
    await session.refresh(flower)
    return flower


async def update_flower_type(
    session: AsyncSession, flower_type_id: int, data: FlowerTypeUpdate
) -> FlowerType:
    flower = await get_flower_type(session, flower_type_id)
    changes = data.model_dump(exclude_unset=True)

    if changes.get("is_active") is False and flower.is_active:
        # Không cho tắt loại hoa đang nằm trong công thức của mẫu đang bán:
        # khách sẽ đặt được mẫu mà shop không còn bán hoa đó.
        used_by = (
            await session.scalars(
                select(BouquetTemplate.name)
                .join(TemplateItem, TemplateItem.template_id == BouquetTemplate.id)
                .where(
                    TemplateItem.flower_type_id == flower.id,
                    BouquetTemplate.is_active.is_(True),
                )
                .order_by(BouquetTemplate.name)
            )
        ).all()
        if used_by:
            raise ConflictError(
                "Flower type is used by active bouquet templates",
                code="FLOWER_IN_USE",
                extra={"templates": list(used_by)},
            )

    _apply_patch(flower, changes, nullable={"image_url"})
    await _commit_unique(session, "Flower type with this name")
    await session.refresh(flower)
    return flower


# =====================================================================
# Nhà cung cấp
# =====================================================================
async def list_suppliers(session: AsyncSession) -> Sequence[Supplier]:
    return (await session.scalars(select(Supplier).order_by(Supplier.name))).all()


async def create_supplier(session: AsyncSession, data: SupplierCreate) -> Supplier:
    supplier = Supplier(**data.model_dump())
    session.add(supplier)
    await _commit_unique(session, "Supplier with this name")
    await session.refresh(supplier)
    return supplier


async def update_supplier(
    session: AsyncSession, supplier_id: int, data: SupplierUpdate
) -> Supplier:
    supplier = await session.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found")
    _apply_patch(supplier, data.model_dump(exclude_unset=True), nullable={"phone", "note"})
    await _commit_unique(session, "Supplier with this name")
    await session.refresh(supplier)
    return supplier


# =====================================================================
# Mẫu bó hoa
# =====================================================================
def _template_query() -> Select[tuple[BouquetTemplate]]:
    return select(BouquetTemplate).options(selectinload(BouquetTemplate.items))


async def get_template(session: AsyncSession, template_id: int) -> BouquetTemplate:
    template = await session.scalar(_template_query().where(BouquetTemplate.id == template_id))
    if template is None:
        raise NotFoundError("Bouquet template not found")
    return template


async def _unique_slug(session: AsyncSession, base: str, exclude_id: int | None = None) -> str:
    """Thêm hậu tố -2, -3… nếu slug đã có."""
    base = base or "mau-bo-hoa"
    stmt = select(BouquetTemplate.slug).where(
        (BouquetTemplate.slug == base) | BouquetTemplate.slug.like(f"{base}-%")
    )
    if exclude_id is not None:
        stmt = stmt.where(BouquetTemplate.id != exclude_id)
    taken = set((await session.scalars(stmt)).all())
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


async def _validate_recipe(session: AsyncSession, items: list[TemplateItemIn]) -> None:
    ids = {i.flower_type_id for i in items}
    rows = (
        await session.execute(
            select(FlowerType.id, FlowerType.is_active).where(FlowerType.id.in_(ids))
        )
    ).all()
    found = {row.id: row.is_active for row in rows}
    missing = sorted(ids - found.keys())
    if missing:
        raise AppError(
            "Unknown flower types in recipe",
            code="UNKNOWN_FLOWER_TYPE",
            extra={"flower_type_ids": missing},
        )
    inactive = sorted(fid for fid, active in found.items() if not active)
    if inactive:
        raise AppError(
            "Recipe uses inactive flower types",
            code="INACTIVE_FLOWER_TYPE",
            extra={"flower_type_ids": inactive},
        )


async def create_template(
    session: AsyncSession, actor: StaffUser, data: TemplateCreate
) -> BouquetTemplate:
    await _validate_recipe(session, data.items)
    slug = data.slug or await _unique_slug(session, slugify(data.name))
    template = BouquetTemplate(
        name=data.name,
        slug=slug,
        description=data.description,
        image_url=data.image_url,
        price=data.price,
        discount_locked=data.discount_locked,
        updated_by_id=actor.id,
        items=[
            TemplateItem(flower_type_id=i.flower_type_id, quantity=i.quantity) for i in data.items
        ],
    )
    session.add(template)
    await _commit_unique(session, "Template with this slug")
    return await get_template(session, template.id)


async def update_template(
    session: AsyncSession, actor: StaffUser, template_id: int, data: TemplateUpdate
) -> BouquetTemplate:
    template = await get_template(session, template_id)
    changes = data.model_dump(exclude_unset=True)

    if changes.get("is_active") is True and not template.is_active:
        # Bật lại mẫu: mọi loại hoa trong công thức phải còn đang bán
        await _validate_recipe(
            session,
            [
                TemplateItemIn(flower_type_id=i.flower_type_id, quantity=i.quantity)
                for i in template.items
            ],
        )

    new_price = changes.get("price")
    if new_price is not None and new_price != template.price:
        session.add(
            TemplatePriceHistory(
                template_id=template.id,
                old_price=template.price,
                new_price=new_price,
                changed_by_id=actor.id,
            )
        )

    _apply_patch(template, changes, nullable={"image_url"})
    template.updated_by_id = actor.id
    await _commit_unique(session, "Template with this slug")
    session.expire(template)
    return await get_template(session, template_id)


async def replace_recipe(
    session: AsyncSession, actor: StaffUser, template_id: int, items: list[TemplateItemIn]
) -> BouquetTemplate:
    template = await get_template(session, template_id)
    await _validate_recipe(session, items)
    template.items.clear()
    await session.flush()  # xóa dòng cũ trước khi chèn lại (cùng khóa chính)
    template.items.extend(
        TemplateItem(flower_type_id=i.flower_type_id, quantity=i.quantity) for i in items
    )
    template.updated_by_id = actor.id
    await session.commit()
    session.expire(template)
    return await get_template(session, template_id)


async def list_templates_admin(
    session: AsyncSession, *, include_inactive: bool = True
) -> Sequence[BouquetTemplate]:
    stmt = _template_query().order_by(BouquetTemplate.name)
    if not include_inactive:
        stmt = stmt.where(BouquetTemplate.is_active.is_(True))
    return (await session.scalars(stmt)).all()


async def price_history(session: AsyncSession, template_id: int) -> Sequence[TemplatePriceHistory]:
    await get_template(session, template_id)
    return (
        await session.scalars(
            select(TemplatePriceHistory)
            .where(TemplatePriceHistory.template_id == template_id)
            .order_by(TemplatePriceHistory.changed_at.desc(), TemplatePriceHistory.id.desc())
        )
    ).all()


# =====================================================================
# Cho khách
# =====================================================================
SORTS = {
    "name": BouquetTemplate.name.asc(),
    "price_asc": BouquetTemplate.price.asc(),
    "price_desc": BouquetTemplate.price.desc(),
    "newest": BouquetTemplate.created_at.desc(),
}


async def list_templates_public(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    min_price: int | None = None,
    max_price: int | None = None,
    sort: str = "name",
) -> tuple[Sequence[BouquetTemplate], int]:
    conditions = [BouquetTemplate.is_active.is_(True)]
    if min_price is not None:
        conditions.append(BouquetTemplate.price >= min_price)
    if max_price is not None:
        conditions.append(BouquetTemplate.price <= max_price)

    total = await session.scalar(
        select(func.count()).select_from(BouquetTemplate).where(*conditions)
    )
    rows = await session.scalars(
        _template_query()
        .where(*conditions)
        .order_by(SORTS[sort], BouquetTemplate.id)
        .limit(limit)
        .offset(offset)
    )
    return rows.all(), total or 0


async def get_template_public(session: AsyncSession, slug: str) -> BouquetTemplate:
    template = await session.scalar(
        _template_query().where(BouquetTemplate.slug == slug, BouquetTemplate.is_active.is_(True))
    )
    if template is None:
        raise NotFoundError("Bouquet template not found")
    return template

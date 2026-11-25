from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.core.errors import AppError
from app.schemas.catalog import TemplatePublicOut
from app.schemas.common import Page
from app.services import catalog, pricing

# Endpoint công khai cho khách — không cần đăng nhập.
router = APIRouter(prefix="/shop", tags=["shop"])


@router.get("/templates", response_model=Page[TemplatePublicOut])
async def list_templates(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
    min_price: Annotated[int | None, Query(ge=0)] = None,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    sort: Literal["name", "price_asc", "price_desc", "newest"] = "name",
) -> Page[TemplatePublicOut]:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise AppError("min_price must not exceed max_price", code="INVALID_PRICE_RANGE")
    rows, total = await catalog.list_templates_public(
        session,
        limit=limit,
        offset=offset,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )
    discounts = await pricing.current_discounts(session, [t.id for t in rows])
    return Page(
        items=[
            TemplatePublicOut.model_validate(t).with_discount(discounts.get(t.id, 0)) for t in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/templates/fresh-today", response_model=list[TemplatePublicOut])
async def fresh_today(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=20)] = 6
) -> list[TemplatePublicOut]:
    """Mục "Tươi nhất hôm nay": mẫu đang được giảm giá / dùng nhiều hoa đang dư thừa nhất."""
    return [
        TemplatePublicOut.model_validate(t).with_discount(pct)
        for t, pct in await pricing.fresh_today(session, limit)
    ]


@router.get("/templates/{slug}", response_model=TemplatePublicOut)
async def get_template(session: SessionDep, slug: str) -> TemplatePublicOut:
    t = await catalog.get_template_public(session, slug)
    pct = (await pricing.current_discounts(session, [t.id])).get(t.id, 0)
    return TemplatePublicOut.model_validate(t).with_discount(pct)

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.core.errors import AppError
from app.models import BouquetTemplate
from app.schemas.catalog import TemplatePublicOut
from app.schemas.common import Page
from app.services import catalog

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
    return Page(
        items=[TemplatePublicOut.model_validate(t) for t in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/templates/{slug}", response_model=TemplatePublicOut)
async def get_template(session: SessionDep, slug: str) -> BouquetTemplate:
    return await catalog.get_template_public(session, slug)

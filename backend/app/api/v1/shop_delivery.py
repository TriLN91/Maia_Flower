from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.core.rate_limit import limit_by_ip
from app.schemas.orders import CartLineIn
from app.services import checkout, maps
from app.services.delivery_fee import compute_fee
from app.services.delivery_quote import issue_quote
from app.services.inventory import utcnow
from app.services.shop_settings import get_delivery_settings

router = APIRouter(prefix="/shop", tags=["shop: delivery"])


class ShopInfoOut(BaseModel):
    shop_address: str
    shop_lat: float
    shop_lng: float
    max_delivery_km: float
    base_fee: int
    base_km: float
    free_ship_min_subtotal: int | None
    free_ship_max_km: float
    hold_minutes: int
    booking_window_days: int
    address_search_enabled: bool


class SuggestionOut(BaseModel):
    place_id: str
    description: str
    main_text: str
    secondary_text: str


class PlaceOut(BaseModel):
    place_id: str
    address: str
    lat: float
    lng: float


class DeliveryQuoteIn(BaseModel):
    lat: Annotated[float, Field(ge=-90, le=90)]
    lng: Annotated[float, Field(ge=-180, le=180)]
    delivery_date: date | None = Field(default=None, description="Để tính phụ phí ngày lễ")
    items: Annotated[list[CartLineIn], Field(max_length=10)] | None = Field(
        default=None, description="Giỏ hàng (tùy chọn) để xét miễn phí ship"
    )


class DeliveryQuoteOut(BaseModel):
    distance_km: float
    provider: str = Field(description="goong = quãng đường thực tế; haversine = ước tính")
    base_fee: int
    distance_fee: int
    holiday_surcharge: int
    free_shipping: bool
    fee: int
    quote_token: str
    expires_at: datetime


@router.get("/info", response_model=ShopInfoOut)
async def shop_info(session: SessionDep) -> ShopInfoOut:
    """Thông tin công khai cho trang đặt hàng: vị trí shop, vùng giao, quy tắc giữ hoa."""
    d = await get_delivery_settings(session)
    s = get_settings()
    return ShopInfoOut(
        shop_address=d.shop_address,
        shop_lat=d.shop_lat,
        shop_lng=d.shop_lng,
        max_delivery_km=d.max_km,
        base_fee=d.base_fee,
        base_km=d.base_km,
        free_ship_min_subtotal=d.free_ship_min_subtotal,
        free_ship_max_km=d.free_ship_max_km,
        hold_minutes=s.hold_minutes,
        booking_window_days=s.booking_window_days,
        address_search_enabled=bool(s.goong_api_key),
    )


@router.get(
    "/address/autocomplete",
    response_model=list[SuggestionOut],
    dependencies=[limit_by_ip("autocomplete", 30, 60)],
)
async def autocomplete(
    session: SessionDep, q: Annotated[str, Query(min_length=3, max_length=200)]
) -> list[maps.PlaceSuggestion]:
    """Gợi ý địa chỉ khi khách gõ (ưu tiên gần shop). Server gọi Goong — API key không lộ ra
    trình duyệt."""
    settings = await get_delivery_settings(session)
    return await maps.search_address(q, (settings.shop_lat, settings.shop_lng))


@router.get(
    "/address/place/{place_id}",
    response_model=PlaceOut,
    dependencies=[limit_by_ip("place", 30, 60)],
)
async def place(place_id: Annotated[str, Path(max_length=300)]) -> maps.Place:
    return await maps.get_place(place_id)


@router.post(
    "/delivery/quote",
    response_model=DeliveryQuoteOut,
    dependencies=[limit_by_ip("delivery-quote", 20, 60)],
)
async def delivery_quote(session: SessionDep, body: DeliveryQuoteIn) -> DeliveryQuoteOut:
    """Đo quãng đường từ shop tới địa chỉ, tính phí và trả về token đã ký (dùng khi đặt hàng)."""
    settings = await get_delivery_settings(session)
    distance = await maps.get_distance((settings.shop_lat, settings.shop_lng), (body.lat, body.lng))

    subtotal = None
    if body.items:
        quote = await checkout.quote_cart(session, body.items, utcnow())
        subtotal = quote.subtotal - quote.discount_total

    fee = compute_fee(
        distance.km, settings=settings, delivery_date=body.delivery_date, subtotal=subtotal
    )
    token, expires_at = issue_quote(
        lat=body.lat,
        lng=body.lng,
        distance_km=fee.distance_km,
        provider=distance.provider,
        now=utcnow(),
    )
    return DeliveryQuoteOut(
        distance_km=fee.distance_km,
        provider=distance.provider,
        base_fee=fee.base_fee,
        distance_fee=fee.distance_fee,
        holiday_surcharge=fee.holiday_surcharge,
        free_shipping=fee.free_shipping,
        fee=fee.total,
        quote_token=token,
        expires_at=expires_at,
    )

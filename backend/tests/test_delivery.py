from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from app.core.config import get_settings
from app.services.delivery_quote import issue_quote
from app.services.maps import haversine_km

QUOTE = "/api/v1/shop/delivery/quote"
GOONG = "https://rsapi.goong.io"
SHOP = (10.7725, 106.6980)  # tọa độ shop mặc định
# Một điểm cách shop ~4,6 km đường chim bay (về phía Bình Thạnh)
DEST = (10.8100, 106.7150)


@pytest.fixture
def goong(monkeypatch):
    """Bật Goong với key giả; mọi request HTTP tới Goong bị respx chặn và giả lập."""
    monkeypatch.setattr(get_settings(), "goong_api_key", "test-goong-key")
    with respx.mock(base_url=GOONG, assert_all_called=False) as mock:
        yield mock


def distance_matrix(meters: int) -> dict:
    return {
        "rows": [
            {
                "elements": [
                    {"status": "OK", "distance": {"value": meters}, "duration": {"value": 900}}
                ]
            }
        ]
    }


# ================================================================ Haversine
def test_haversine_known_distance():
    # 1 độ vĩ dọc kinh tuyến = π × R / 180 ≈ 111,195 km (R = 6 371,0088 km)
    assert haversine_km(10.0, 106.7, 11.0, 106.7) == pytest.approx(111.195, abs=0.01)
    assert haversine_km(10.7725, 106.698, 10.7725, 106.698) == 0


async def test_quote_without_goong_uses_haversine(client):
    r = await client.post(QUOTE, json={"lat": DEST[0], "lng": DEST[1]})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["provider"] == "haversine"
    expected_km = haversine_km(*SHOP, *DEST) * 1.3
    assert q["distance_km"] == pytest.approx(expected_km, abs=0.1)
    assert q["fee"] == q["base_fee"] + q["distance_fee"]
    assert q["quote_token"]


async def test_out_of_range_address(client):
    r = await client.post(QUOTE, json={"lat": 21.0285, "lng": 105.8542})  # Hà Nội
    assert r.status_code == 400
    assert r.json()["code"] == "OUT_OF_DELIVERY_RANGE"


# ================================================================ Goong (giả lập)
async def test_quote_uses_goong_road_distance(client, goong):
    route = goong.get("/DistanceMatrix").mock(
        return_value=httpx.Response(200, json=distance_matrix(7400))
    )

    q = (await client.post(QUOTE, json={"lat": DEST[0], "lng": DEST[1]})).json()
    assert q["provider"] == "goong"
    assert q["distance_km"] == 7.4
    assert q["fee"] == 42_000

    sent = route.calls.last.request.url.params
    assert sent["vehicle"] == "bike"
    assert sent["api_key"] == "test-goong-key"
    assert sent["origins"] == f"{SHOP[0]},{SHOP[1]}"


async def test_distance_is_cached(client, goong):
    route = goong.get("/DistanceMatrix").mock(
        return_value=httpx.Response(200, json=distance_matrix(5000))
    )
    for _ in range(3):
        await client.post(QUOTE, json={"lat": DEST[0], "lng": DEST[1]})
    assert route.call_count == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"status": "REQUEST_DENIED"}),
        httpx.Response(200, json={"rows": [{"elements": [{"status": "ZERO_RESULTS"}]}]}),
        httpx.Response(200, json={"unexpected": "shape"}),
    ],
    ids=["http-500", "denied", "no-route", "bad-json"],
)
async def test_goong_failure_falls_back_to_haversine(client, goong, response):
    goong.get("/DistanceMatrix").mock(return_value=response)
    r = await client.post(QUOTE, json={"lat": DEST[0], "lng": DEST[1]})
    assert r.status_code == 200
    assert r.json()["provider"] == "haversine"


async def test_goong_timeout_falls_back(client, goong):
    goong.get("/DistanceMatrix").mock(side_effect=httpx.ConnectTimeout("slow"))
    r = await client.post(QUOTE, json={"lat": DEST[0], "lng": DEST[1]})
    assert r.json()["provider"] == "haversine"


async def test_autocomplete_and_place_detail(client, goong):
    goong.get("/Place/AutoComplete").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "predictions": [
                    {
                        "place_id": "abc123",
                        "description": "12 Nguyễn Huệ, Bến Nghé, Quận 1",
                        "structured_formatting": {
                            "main_text": "12 Nguyễn Huệ",
                            "secondary_text": "Bến Nghé, Quận 1",
                        },
                    }
                ],
            },
        )
    )
    goong.get("/Place/Detail").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "result": {
                    "formatted_address": "12 Nguyễn Huệ, Bến Nghé, Quận 1, TP.HCM",
                    "geometry": {"location": {"lat": 10.7743, "lng": 106.7038}},
                },
            },
        )
    )

    r = await client.get("/api/v1/shop/address/autocomplete", params={"q": "12 nguyen hue"})
    assert r.status_code == 200
    assert r.json()[0] == {
        "place_id": "abc123",
        "description": "12 Nguyễn Huệ, Bến Nghé, Quận 1",
        "main_text": "12 Nguyễn Huệ",
        "secondary_text": "Bến Nghé, Quận 1",
    }
    place = (await client.get("/api/v1/shop/address/place/abc123")).json()
    assert (place["lat"], place["lng"]) == (10.7743, 106.7038)


async def test_autocomplete_without_goong_returns_503(client):
    r = await client.get("/api/v1/shop/address/autocomplete", params={"q": "nguyen hue"})
    assert r.status_code == 503
    assert r.json()["code"] == "ADDRESS_SEARCH_UNAVAILABLE"


# ================================================================ Token báo giá
def test_quote_token_rejected_as_login_token():
    """Token báo giá ký cùng khóa nhưng khác audience: không dùng để đăng nhập được."""
    from app.core.security import decode_access_token

    token, _ = issue_quote(lat=1, lng=1, distance_km=1, provider="x", now=datetime.now(UTC))
    with pytest.raises(Exception):  # noqa: B017
        decode_access_token(token)


# ================================================================ Cài đặt giao hàng
async def test_owner_updates_delivery_settings(client, owner_headers):
    url = "/api/v1/admin/settings/delivery"
    current = (await client.get(url, headers=owner_headers)).json()
    assert current["base_fee"] == 20_000

    current.update(base_fee=25_000, max_km=10, tiers=[{"to_km": 10, "per_km": 6_000}])
    r = await client.put(url, json=current, headers=owner_headers)
    assert r.status_code == 200

    # Báo giá dùng ngay bảng phí mới
    q = (await client.post(QUOTE, json={"lat": DEST[0], "lng": DEST[1]})).json()
    assert q["base_fee"] == 25_000

    bad = {**current, "max_km": 30}  # bậc cuối không phủ tới 30 km
    assert (await client.put(url, json=bad, headers=owner_headers)).status_code == 422


async def test_delivery_settings_owner_only(client, make_staff, login):
    await make_staff(email="tho@maiaflower.vn")
    headers = await login("tho@maiaflower.vn")
    assert (await client.get("/api/v1/admin/settings/delivery", headers=headers)).status_code == 403


# ================================================================ Quản lý khung giờ
async def test_slot_admin_crud_and_overlap(client, owner_headers):
    url = "/api/v1/admin/delivery-slots"
    r = await client.post(
        url,
        json={"start_time": "08:00", "end_time": "10:00", "default_capacity": 6},
        headers=owner_headers,
    )
    assert r.status_code == 201
    slot_id = r.json()["id"]

    clash = await client.post(
        url,
        json={"start_time": "09:00", "end_time": "11:00", "default_capacity": 3},
        headers=owner_headers,
    )
    assert clash.status_code == 400
    assert clash.json()["code"] == "SLOT_OVERLAP"

    adjacent = await client.post(
        url,
        json={"start_time": "10:00", "end_time": "12:00", "default_capacity": 3},
        headers=owner_headers,
    )
    assert adjacent.status_code == 201  # sát nhau nhưng không chồng

    bad = await client.post(
        url,
        json={"start_time": "12:00", "end_time": "11:00", "default_capacity": 3},
        headers=owner_headers,
    )
    assert bad.status_code == 422

    r = await client.patch(f"{url}/{slot_id}", json={"default_capacity": 10}, headers=owner_headers)
    assert r.json()["default_capacity"] == 10


async def test_override_slot_day(client, owner_headers):
    slot = (
        await client.post(
            "/api/v1/admin/delivery-slots",
            json={"start_time": "17:00", "end_time": "19:00", "default_capacity": 6},
            headers=owner_headers,
        )
    ).json()
    day = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()

    r = await client.put(
        f"/api/v1/admin/delivery-slots/{slot['id']}/days/{day}",
        json={"capacity": 15},
        headers=owner_headers,
    )
    assert r.status_code == 200
    assert (r.json()["capacity"], r.json()["overridden"]) == (15, True)

    listed = (
        await client.get(
            "/api/v1/admin/delivery-slot-days", params={"date": day}, headers=owner_headers
        )
    ).json()
    assert listed[0]["capacity"] == 15

    shop = (await client.get("/api/v1/shop/delivery-slots", params={"date": day})).json()
    assert shop[0]["remaining"] == 15

    closed = await client.put(
        f"/api/v1/admin/delivery-slots/{slot['id']}/days/{day}",
        json={"is_closed": True},
        headers=owner_headers,
    )
    assert closed.json()["is_closed"] is True
    shop = (await client.get("/api/v1/shop/delivery-slots", params={"date": day})).json()
    assert (shop[0]["bookable"], shop[0]["reason"]) == (False, "CLOSED")


async def test_public_shop_info(client):
    info = (await client.get("/api/v1/shop/info")).json()
    assert (info["shop_lat"], info["shop_lng"]) == SHOP
    assert info["max_delivery_km"] == 15
    assert info["hold_minutes"] == 15
    assert info["address_search_enabled"] is False


async def test_payment_return_url_can_point_to_frontend(monkeypatch):
    from app.services.payments.provider import get_provider

    monkeypatch.setattr(
        get_settings(), "payment_return_url", "http://localhost:5173/payment-result"
    )
    url = get_provider().payment_url(
        txn_ref="T1",
        amount=1000,
        order_info="x",
        now=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    assert "vnp_ReturnUrl=http%3A%2F%2Flocalhost%3A5173%2Fpayment-result" in url

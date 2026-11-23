"""Bản đồ: gợi ý địa chỉ, tọa độ địa điểm, quãng đường.

- Có GOONG_API_KEY -> gọi Goong (quãng đường xe máy thực tế).
- Không có key, hoặc Goong lỗi/chậm -> Haversine (đường chim bay) × hệ số đường vòng.
- Kết quả được cache trong Redis để giảm số lần gọi API (Goong tính phí theo lượt).

LƯU Ý: định dạng request/response của Goong ở đây theo chuẩn tương thích Google Places mà Goong
dùng; chưa kiểm chứng với API thật (chưa có key). Toàn bộ phần đọc phản hồi gom trong
`GoongClient` để dễ chỉnh khi gắn key.
"""

import hashlib
import json
import logging
import math
from dataclasses import asdict, dataclass

import httpx

from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.core.redis import get_redis

log = logging.getLogger(__name__)

DISTANCE_TTL = 7 * 86400
FALLBACK_DISTANCE_TTL = 3600  # kết quả dự phòng chỉ cache ngắn: Goong hồi phục là dùng lại ngay
AUTOCOMPLETE_TTL = 86400
PLACE_TTL = 30 * 86400


class MapsError(Exception):
    """Goong trả lỗi / dữ liệu không đọc được."""


@dataclass(frozen=True)
class DistanceResult:
    km: float
    provider: str  # "goong" | "haversine"


@dataclass(frozen=True)
class PlaceSuggestion:
    place_id: str
    description: str
    main_text: str
    secondary_text: str


@dataclass(frozen=True)
class Place:
    place_id: str
    address: str
    lat: float
    lng: float


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088  # bán kính trung bình Trái Đất (km)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class GoongClient:
    def __init__(self, api_key: str, base_url: str, timeout: float):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str, params: dict) -> dict:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            r = await client.get(path, params={**params, "api_key": self.api_key})
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "OK")
        if status not in ("OK", "ZERO_RESULTS"):
            raise MapsError(f"Goong status {status}")
        return data

    async def autocomplete(self, text: str, near: tuple[float, float]) -> list[PlaceSuggestion]:
        data = await self._get(
            "/Place/AutoComplete",
            {"input": text, "location": f"{near[0]},{near[1]}", "limit": 5},
        )
        out = []
        for p in data.get("predictions", []):
            fmt = p.get("structured_formatting") or {}
            out.append(
                PlaceSuggestion(
                    place_id=p["place_id"],
                    description=p["description"],
                    main_text=fmt.get("main_text", p["description"]),
                    secondary_text=fmt.get("secondary_text", ""),
                )
            )
        return out

    async def place_detail(self, place_id: str) -> Place:
        data = await self._get("/Place/Detail", {"place_id": place_id})
        result = data.get("result")
        if not result:
            raise NotFoundError("Place not found", code="PLACE_NOT_FOUND")
        loc = result["geometry"]["location"]
        return Place(
            place_id=place_id,
            address=result.get("formatted_address") or result.get("name", ""),
            lat=float(loc["lat"]),
            lng=float(loc["lng"]),
        )

    async def distance_km(self, origin: tuple[float, float], dest: tuple[float, float]) -> float:
        data = await self._get(
            "/DistanceMatrix",
            {
                "origins": f"{origin[0]},{origin[1]}",
                "destinations": f"{dest[0]},{dest[1]}",
                "vehicle": "bike",  # shop giao bằng xe máy
            },
        )
        element = data["rows"][0]["elements"][0]
        if element.get("status", "OK") != "OK":
            raise MapsError(f"Route status {element.get('status')}")
        return element["distance"]["value"] / 1000  # mét -> km


def _goong() -> GoongClient | None:
    s = get_settings()
    if not s.goong_api_key:
        return None
    return GoongClient(s.goong_api_key, s.goong_base_url, s.goong_timeout_seconds)


def _coord_key(lat: float, lng: float) -> str:
    return f"{lat:.4f},{lng:.4f}"  # ~11 m: đủ chính xác cho tính phí, tăng tỷ lệ trúng cache


async def get_distance(origin: tuple[float, float], dest: tuple[float, float]) -> DistanceResult:
    redis = get_redis()
    key = f"maps:dist:{_coord_key(*origin)}:{_coord_key(*dest)}"
    if cached := await redis.get(key):
        return DistanceResult(**json.loads(cached))

    result: DistanceResult | None = None
    if client := _goong():
        try:
            result = DistanceResult(round(await client.distance_km(origin, dest), 3), "goong")
        except (httpx.HTTPError, MapsError, KeyError, IndexError, TypeError, ValueError) as e:
            log.warning("Goong distance failed, falling back to haversine: %r", e)

    if result is None:
        km = haversine_km(*origin, *dest) * get_settings().road_factor
        result = DistanceResult(round(km, 3), "haversine")

    ttl = DISTANCE_TTL if result.provider == "goong" else FALLBACK_DISTANCE_TTL
    await redis.set(key, json.dumps(asdict(result)), ex=ttl)
    return result


def _require_goong() -> GoongClient:
    client = _goong()
    if client is None:
        raise AppError(
            "Address search is not configured; please pin your location on the map",
            code="ADDRESS_SEARCH_UNAVAILABLE",
            status_code=503,
        )
    return client


async def search_address(text: str, near: tuple[float, float]) -> list[PlaceSuggestion]:
    client = _require_goong()
    redis = get_redis()
    digest = hashlib.sha256(text.strip().lower().encode()).hexdigest()[:32]
    key = f"maps:ac:{digest}"
    if cached := await redis.get(key):
        return [PlaceSuggestion(**p) for p in json.loads(cached)]
    try:
        results = await client.autocomplete(text.strip(), near)
    except (httpx.HTTPError, MapsError, KeyError, TypeError) as e:
        log.warning("Goong autocomplete failed: %r", e)
        raise AppError(
            "Address search is temporarily unavailable",
            code="ADDRESS_SEARCH_UNAVAILABLE",
            status_code=503,
        ) from None
    await redis.set(key, json.dumps([asdict(p) for p in results]), ex=AUTOCOMPLETE_TTL)
    return results


async def get_place(place_id: str) -> Place:
    client = _require_goong()
    redis = get_redis()
    key = f"maps:place:{hashlib.sha256(place_id.encode()).hexdigest()[:32]}"
    if cached := await redis.get(key):
        return Place(**json.loads(cached))
    try:
        place = await client.place_detail(place_id)
    except (httpx.HTTPError, MapsError, KeyError, TypeError, ValueError) as e:
        log.warning("Goong place detail failed: %r", e)
        raise AppError(
            "Address lookup is temporarily unavailable",
            code="ADDRESS_SEARCH_UNAVAILABLE",
            status_code=503,
        ) from None
    await redis.set(key, json.dumps(asdict(place)), ex=PLACE_TTL)
    return place

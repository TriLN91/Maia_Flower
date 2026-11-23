"""Báo giá ship có chữ ký.

Server đo quãng đường một lần ở bước nhập địa chỉ rồi ký (JWT, HMAC-SHA256) vào token có hạn.
Lúc đặt hàng, server chỉ tin tọa độ + quãng đường trong token — khách không thể tự sửa
quãng đường để giảm phí, và không phải gọi API bản đồ thêm lần nữa.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

from app.core.config import get_settings
from app.core.errors import AppError

AUDIENCE = "maia:delivery-quote"


@dataclass(frozen=True)
class QuoteClaims:
    lat: float
    lng: float
    distance_km: float
    provider: str


def issue_quote(
    *, lat: float, lng: float, distance_km: float, provider: str, now: datetime
) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = now + timedelta(minutes=settings.delivery_quote_minutes)
    token = jwt.encode(
        {
            "aud": AUDIENCE,
            "lat": lat,
            "lng": lng,
            "km": distance_km,
            "prov": provider,
            "iat": now,
            "exp": expires_at,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def verify_quote(token: str) -> QuoteClaims:
    settings = get_settings()
    try:
        c = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=AUDIENCE,  # token đăng nhập không dùng thay được (khác audience)
            options={"require": ["aud", "exp", "lat", "lng", "km"]},
        )
    except jwt.ExpiredSignatureError:
        raise AppError(
            "Delivery quote has expired, please re-check the address",
            code="DELIVERY_QUOTE_EXPIRED",
        ) from None
    except jwt.PyJWTError:
        raise AppError("Invalid delivery quote", code="INVALID_DELIVERY_QUOTE") from None
    return QuoteClaims(float(c["lat"]), float(c["lng"]), float(c["km"]), str(c.get("prov", "")))

"""Ký và kiểm tra chữ ký theo chuẩn VNPay 2.1.0.

hashData = các tham số `vnp_*` (trừ vnp_SecureHash, vnp_SecureHashType) có giá trị khác rỗng,
sắp theo tên tăng dần, nối dạng `key=urlencode(value)` bằng `&`;
vnp_SecureHash = HMAC-SHA512(hashSecret, hashData) dạng hex.
"""

import hashlib
import hmac
from collections.abc import Mapping
from urllib.parse import quote_plus, urlencode

EXCLUDED = {"vnp_SecureHash", "vnp_SecureHashType"}


def hash_data(params: Mapping[str, str]) -> str:
    items = sorted(
        (k, str(v)) for k, v in params.items() if k.startswith("vnp_") and k not in EXCLUDED and v
    )
    return "&".join(f"{k}={quote_plus(v)}" for k, v in items)


def sign(params: Mapping[str, str], secret: str) -> str:
    return hmac.new(secret.encode(), hash_data(params).encode(), hashlib.sha512).hexdigest()


def signed_query(params: Mapping[str, str], secret: str) -> str:
    """Query string đã kèm chữ ký."""
    return urlencode({**params, "vnp_SecureHash": sign(params, secret)})


def verify(params: Mapping[str, str], secret: str) -> bool:
    given = params.get("vnp_SecureHash", "")
    # so sánh hằng thời gian: không lộ chữ ký đúng qua thời gian phản hồi
    return bool(given) and hmac.compare_digest(given.lower(), sign(params, secret))

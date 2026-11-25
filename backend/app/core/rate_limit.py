"""Giới hạn tần suất bằng Redis — cửa sổ trượt (sliding window log).

Mỗi khóa (vd. "login:ip:1.2.3.4") là một sorted set chứa thời điểm các request trong cửa sổ.
Toàn bộ "dọn cũ → đếm → thêm" chạy trong MỘT script Lua nên nguyên tử: nhiều request song song
không thể cùng lọt qua khi chỉ còn 1 lượt.

Khác cửa sổ cố định (INCR + EXPIRE), cửa sổ trượt không cho dồn 2× giới hạn quanh ranh giới
phút (vd. 5 request lúc 0:59 + 5 request lúc 1:00).
"""

import logging
import math
import secrets
import time
from collections.abc import Callable

from fastapi import Depends, Request
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.errors import RateLimitedError
from app.core.redis import get_redis

log = logging.getLogger(__name__)

_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
if redis.call('ZCARD', key) >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, math.ceil(tonumber(oldest[2]) + window - now)}
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('PEXPIRE', key, window)
return {1, 0}
"""


async def enforce(key: str, limit: int, window_seconds: int) -> None:
    """Ném RateLimitedError (429 + Retry-After) nếu vượt giới hạn.

    Redis lỗi -> cho qua (fail-open) và ghi log: thà tạm mất lớp chống spam còn hơn chặn
    toàn bộ khách đặt hoa.
    """
    if not get_settings().rate_limit_enabled:
        return
    now_ms = int(time.time() * 1000)
    try:
        allowed, retry_ms = await get_redis().eval(
            _SLIDING_WINDOW,
            1,
            f"rl:{key}",
            now_ms,
            window_seconds * 1000,
            limit,
            f"{now_ms}-{secrets.token_hex(4)}",
        )
    except RedisError as e:
        log.warning("Rate limiter unavailable, allowing request: %r", e)
        return
    if not allowed:
        retry_after = max(1, math.ceil(int(retry_ms) / 1000))
        raise RateLimitedError(
            "Too many requests, please try again later",
            extra={"retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit_by_ip(name: str, limit: int, window_seconds: int) -> Callable:
    """Dependency cho route: `dependencies=[limit_by_ip("login", 5, 60)]`."""

    async def _dependency(request: Request) -> None:
        await enforce(f"{name}:ip:{client_ip(request)}", limit, window_seconds)

    return Depends(_dependency)

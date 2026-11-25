import asyncio

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import rate_limit
from app.core.config import get_settings
from app.core.errors import RateLimitedError


@pytest.fixture(autouse=True)
def enable_rate_limit(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)


async def test_sliding_window_allows_up_to_limit():
    for _ in range(3):
        await rate_limit.enforce("unit:a", 3, 60)
    with pytest.raises(RateLimitedError) as e:
        await rate_limit.enforce("unit:a", 3, 60)
    assert e.value.status_code == 429
    assert 1 <= e.value.extra["retry_after"] <= 60
    assert e.value.headers == {"Retry-After": str(e.value.extra["retry_after"])}
    await rate_limit.enforce("unit:b", 3, 60)  # khóa khác không bị ảnh hưởng


async def test_window_slides(monkeypatch):
    clock = [1_000.0]
    monkeypatch.setattr(rate_limit.time, "time", lambda: clock[0])
    await rate_limit.enforce("unit:slide", 2, 10)
    clock[0] += 6
    await rate_limit.enforce("unit:slide", 2, 10)
    with pytest.raises(RateLimitedError) as e:
        await rate_limit.enforce("unit:slide", 2, 10)
    assert e.value.extra["retry_after"] == 4  # request đầu rơi khỏi cửa sổ sau 4 giây nữa
    clock[0] += 4.001
    await rate_limit.enforce("unit:slide", 2, 10)


async def test_limit_is_atomic_under_concurrency():
    """30 request song song, giới hạn 5: đúng 5 lọt qua (script Lua nguyên tử)."""

    async def hit():
        try:
            await rate_limit.enforce("unit:race", 5, 60)
            return True
        except RateLimitedError:
            return False

    results = await asyncio.gather(*[hit() for _ in range(30)])
    assert sum(results) == 5


async def test_fail_open_when_redis_is_down(monkeypatch):
    class Broken:
        async def eval(self, *args):
            raise RedisConnectionError("down")

    monkeypatch.setattr(rate_limit, "get_redis", lambda: Broken())
    await rate_limit.enforce("unit:down", 1, 60)
    await rate_limit.enforce("unit:down", 1, 60)  # không ném lỗi


async def test_disabled_flag(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    for _ in range(10):
        await rate_limit.enforce("unit:off", 1, 60)


# ---------------------------------------------------------------- qua API
async def test_login_is_rate_limited_per_ip(client):
    for _ in range(5):
        r = await client.post(
            "/api/v1/auth/login", data={"username": "x@maiaflower.vn", "password": "wrong-pass"}
        )
        assert r.status_code == 401
    r = await client.post(
        "/api/v1/auth/login", data={"username": "y@maiaflower.vn", "password": "wrong-pass"}
    )
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"
    assert "retry-after" in r.headers


async def test_login_is_rate_limited_per_email_across_ips(client, monkeypatch):
    """Dò mật khẩu một tài khoản từ nhiều IP (giả lập bằng X-Forwarded-For sau proxy tin cậy)."""
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    for i in range(10):
        r = await client.post(
            "/api/v1/auth/login",
            data={"username": "boss@maiaflower.vn", "password": "guess"},
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        )
        assert r.status_code == 401
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": "boss@maiaflower.vn", "password": "guess"},
        headers={"X-Forwarded-For": "10.0.0.99"},
    )
    assert r.status_code == 429


async def test_forwarded_header_ignored_without_trusted_proxy(client):
    """Không có proxy tin cậy: khách đổi X-Forwarded-For cũng không lách được giới hạn IP."""
    for i in range(5):
        await client.post(
            "/api/v1/auth/login",
            data={"username": f"u{i}@maiaflower.vn", "password": "wrong-pass"},
            headers={"X-Forwarded-For": f"1.2.3.{i}"},
        )
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": "z@maiaflower.vn", "password": "wrong-pass"},
        headers={"X-Forwarded-For": "9.9.9.9"},
    )
    assert r.status_code == 429


async def test_autocomplete_is_rate_limited(client):
    statuses = [
        (
            await client.get("/api/v1/shop/address/autocomplete", params={"q": "nguyen hue"})
        ).status_code
        for _ in range(31)
    ]
    assert statuses[:30] == [503] * 30  # chưa cấu hình Goong, nhưng vẫn tính lượt
    assert statuses[30] == 429

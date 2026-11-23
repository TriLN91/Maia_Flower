from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.models import StaffRole
from tests.conftest import DEFAULT_PASSWORD

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


async def test_login_returns_token_and_me_works(client, make_staff, login):
    await make_staff(email="tho@maiaflower.vn", full_name="Thợ Lan")
    headers = await login("tho@maiaflower.vn")

    r = await client.get(ME, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "tho@maiaflower.vn"
    assert body["role"] == "staff"
    assert "password_hash" not in body


async def test_login_email_is_case_insensitive(client, make_staff):
    await make_staff(email="tho@maiaflower.vn")
    r = await client.post(
        LOGIN, data={"username": "  THO@maiaflower.vn ", "password": DEFAULT_PASSWORD}
    )
    assert r.status_code == 200


async def test_wrong_password_and_unknown_email_get_same_error(client, make_staff):
    await make_staff(email="tho@maiaflower.vn")
    wrong_pw = await client.post(
        LOGIN, data={"username": "tho@maiaflower.vn", "password": "nope-nope"}
    )
    unknown = await client.post(
        LOGIN, data={"username": "ghost@maiaflower.vn", "password": "nope-nope"}
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()  # không tiết lộ email nào tồn tại


async def test_me_requires_token(client):
    assert (await client.get(ME)).status_code == 401


async def test_tampered_and_expired_tokens_are_rejected(client, make_staff):
    user = await make_staff()
    settings = get_settings()
    now = datetime.now(UTC)
    base = {"sub": str(user.id), "role": "staff", "type": "access", "iat": now}

    forged = jwt.encode({**base, "exp": now + timedelta(hours=1)}, "x" * 40, algorithm="HS256")
    expired = jwt.encode(
        {**base, "exp": now - timedelta(seconds=1)}, settings.jwt_secret, algorithm="HS256"
    )
    wrong_type = jwt.encode(
        {**base, "type": "refresh", "exp": now + timedelta(hours=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    for token in (forged, expired, wrong_type, "not-a-jwt"):
        r = await client.get(ME, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, token


async def test_deactivated_user_cannot_login_and_old_token_stops_working(
    client, make_staff, login, owner_headers
):
    user = await make_staff(email="tho@maiaflower.vn")
    staff_headers = await login("tho@maiaflower.vn")

    r = await client.patch(
        f"/api/v1/staff/{user.id}", json={"is_active": False}, headers=owner_headers
    )
    assert r.status_code == 200

    assert (await client.get(ME, headers=staff_headers)).status_code == 401
    r = await client.post(
        LOGIN, data={"username": "tho@maiaflower.vn", "password": DEFAULT_PASSWORD}
    )
    assert r.status_code == 401


async def test_change_password(client, make_staff, login):
    await make_staff(email="tho@maiaflower.vn")
    headers = await login("tho@maiaflower.vn")

    bad = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong-one", "new_password": "brand-new-pass"},
        headers=headers,
    )
    assert bad.status_code == 400

    ok = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "brand-new-pass"},
        headers=headers,
    )
    assert ok.status_code == 204
    await login("tho@maiaflower.vn", "brand-new-pass")


async def test_token_carries_role(client, make_staff, login):
    await make_staff(email="boss@maiaflower.vn", role=StaffRole.OWNER)
    headers = await login("boss@maiaflower.vn")
    token = headers["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    assert claims["role"] == "owner"

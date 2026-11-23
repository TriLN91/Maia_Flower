from app.models import StaffRole

STAFF = "/api/v1/staff"


async def test_staff_role_cannot_manage_staff(client, make_staff, login):
    await make_staff(email="tho@maiaflower.vn")
    headers = await login("tho@maiaflower.vn")
    assert (await client.get(STAFF, headers=headers)).status_code == 403
    r = await client.post(
        STAFF,
        json={"email": "x@maiaflower.vn", "full_name": "X", "password": "password123"},
        headers=headers,
    )
    assert r.status_code == 403


async def test_owner_creates_and_lists_staff(client, owner_headers, login):
    r = await client.post(
        STAFF,
        json={"email": "New.Tho@maiaflower.vn", "full_name": "Thợ Mới", "password": "password123"},
        headers=owner_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "new.tho@maiaflower.vn"
    assert r.json()["role"] == "staff"

    await login("new.tho@maiaflower.vn", "password123")

    listed = await client.get(STAFF, headers=owner_headers)
    assert [u["email"] for u in listed.json()] == ["owner@maiaflower.vn", "new.tho@maiaflower.vn"]


async def test_duplicate_email_is_rejected_case_insensitively(client, owner_headers):
    payload = {"email": "dup@maiaflower.vn", "full_name": "A", "password": "password123"}
    assert (await client.post(STAFF, json=payload, headers=owner_headers)).status_code == 201
    payload["email"] = "DUP@maiaflower.vn"
    r = await client.post(STAFF, json=payload, headers=owner_headers)
    assert r.status_code == 409


async def test_validation_errors(client, owner_headers):
    r = await client.post(
        STAFF,
        json={"email": "not-an-email", "full_name": "", "password": "short"},
        headers=owner_headers,
    )
    assert r.status_code == 422
    bad_fields = {e["loc"][-1] for e in r.json()["detail"]}
    assert bad_fields == {"email", "full_name", "password"}


async def test_owner_cannot_demote_or_deactivate_self(client, owner_headers):
    me = (await client.get("/api/v1/auth/me", headers=owner_headers)).json()
    for change in ({"role": "staff"}, {"is_active": False}):
        r = await client.patch(f"{STAFF}/{me['id']}", json=change, headers=owner_headers)
        assert r.status_code == 400


async def test_owner_can_demote_another_owner(client, owner_headers, make_staff):
    other = await make_staff(email="owner2@maiaflower.vn", role=StaffRole.OWNER)
    r = await client.patch(f"{STAFF}/{other.id}", json={"role": "staff"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["role"] == "staff"


async def test_owner_resets_staff_password(client, owner_headers, make_staff, login):
    user = await make_staff(email="tho@maiaflower.vn")
    r = await client.patch(
        f"{STAFF}/{user.id}", json={"password": "reset-pass-99"}, headers=owner_headers
    )
    assert r.status_code == 200
    await login("tho@maiaflower.vn", "reset-pass-99")


async def test_update_unknown_staff_returns_404(client, owner_headers):
    r = await client.patch(f"{STAFF}/9999", json={"full_name": "X"}, headers=owner_headers)
    assert r.status_code == 404

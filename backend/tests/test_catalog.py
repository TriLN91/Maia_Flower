import pytest

FT = "/api/v1/admin/flower-types"
SUP = "/api/v1/admin/suppliers"
TPL = "/api/v1/admin/templates"


@pytest.fixture
async def staff_headers(make_staff, login):
    await make_staff(email="tho@maiaflower.vn")
    return await login("tho@maiaflower.vn")


@pytest.fixture
def new_flower(client, owner_headers):
    async def _new(name: str, **overrides) -> dict:
        body = {"name": name, "color": "đỏ", "vase_life_days": 7, "reference_cost": 8000}
        r = await client.post(FT, json={**body, **overrides}, headers=owner_headers)
        assert r.status_code == 201, r.text
        return r.json()

    return _new


@pytest.fixture
def new_template(client, owner_headers):
    async def _new(name: str, items: list[tuple[int, int]], price: int = 450_000, **extra) -> dict:
        body = {
            "name": name,
            "price": price,
            "items": [{"flower_type_id": f, "quantity": q} for f, q in items],
            **extra,
        }
        r = await client.post(TPL, json=body, headers=owner_headers)
        assert r.status_code == 201, r.text
        return r.json()

    return _new


# ---------------------------------------------------------------- Loại hoa
async def test_owner_creates_flower_type_and_staff_can_view(
    client, owner_headers, staff_headers, new_flower
):
    created = await new_flower("  Hồng   đỏ Đà Lạt ")
    assert created["name"] == "Hồng đỏ Đà Lạt"  # khoảng trắng được chuẩn hóa
    assert created["is_active"] is True

    r = await client.get(FT, headers=staff_headers)
    assert r.status_code == 200
    assert [f["name"] for f in r.json()] == ["Hồng đỏ Đà Lạt"]


async def test_staff_cannot_modify_catalog(client, staff_headers):
    r = await client.post(
        FT, json={"name": "Cúc", "color": "vàng", "vase_life_days": 10}, headers=staff_headers
    )
    assert r.status_code == 403


async def test_anonymous_cannot_access_admin(client):
    assert (await client.get(FT)).status_code == 401
    assert (await client.get(TPL)).status_code == 401


async def test_duplicate_flower_name_returns_conflict_code(client, owner_headers, new_flower):
    await new_flower("Baby trắng")
    r = await client.post(
        FT,
        json={"name": "Baby trắng", "color": "trắng", "vase_life_days": 10},
        headers=owner_headers,
    )
    assert r.status_code == 409
    assert r.json()["code"] == "DUPLICATE"


async def test_flower_type_validation(client, owner_headers):
    r = await client.post(
        FT,
        json={"name": "", "color": "x", "vase_life_days": 0, "reference_cost": -1},
        headers=owner_headers,
    )
    assert r.status_code == 422
    assert {e["loc"][-1] for e in r.json()["detail"]} == {
        "name",
        "vase_life_days",
        "reference_cost",
    }


async def test_patch_rejects_null_for_required_field(client, owner_headers, new_flower):
    flower = await new_flower("Cúc tana")
    r = await client.patch(f"{FT}/{flower['id']}", json={"name": None}, headers=owner_headers)
    assert r.status_code == 400
    assert r.json()["code"] == "NULL_NOT_ALLOWED"


async def test_cannot_deactivate_flower_used_by_active_template(
    client, owner_headers, new_flower, new_template
):
    rose = await new_flower("Hồng đỏ")
    tpl = await new_template("Đỏ Rực", [(rose["id"], 10)])

    r = await client.patch(f"{FT}/{rose['id']}", json={"is_active": False}, headers=owner_headers)
    assert r.status_code == 409
    assert r.json()["code"] == "FLOWER_IN_USE"
    assert r.json()["extra"]["templates"] == ["Đỏ Rực"]

    # Tắt mẫu trước thì tắt được hoa
    await client.patch(f"{TPL}/{tpl['id']}", json={"is_active": False}, headers=owner_headers)
    r = await client.patch(f"{FT}/{rose['id']}", json={"is_active": False}, headers=owner_headers)
    assert r.status_code == 200

    # …và không bật lại mẫu được khi hoa đã ngừng bán
    r = await client.patch(f"{TPL}/{tpl['id']}", json={"is_active": True}, headers=owner_headers)
    assert r.status_code == 400
    assert r.json()["code"] == "INACTIVE_FLOWER_TYPE"


# ---------------------------------------------------------------- Nhà cung cấp
async def test_supplier_crud(client, owner_headers, staff_headers):
    r = await client.post(
        SUP, json={"name": "Vườn hoa Đà Lạt", "phone": "0909 123 456"}, headers=owner_headers
    )
    assert r.status_code == 201
    sid = r.json()["id"]

    r = await client.patch(
        f"{SUP}/{sid}", json={"note": "Giao thứ 2, 5", "phone": None}, headers=owner_headers
    )
    assert r.status_code == 200
    assert r.json()["note"] == "Giao thứ 2, 5"
    assert r.json()["phone"] is None

    r = await client.get(SUP, headers=staff_headers)
    assert [s["name"] for s in r.json()] == ["Vườn hoa Đà Lạt"]

    bad = await client.post(SUP, json={"name": "X", "phone": "abc"}, headers=owner_headers)
    assert bad.status_code == 422


# ---------------------------------------------------------------- Mẫu bó hoa
async def test_create_template_with_recipe_and_auto_slug(new_flower, new_template):
    rose = await new_flower("Hồng phấn")
    baby = await new_flower("Baby trắng", color="trắng")
    tpl = await new_template("Pastel Ngọt Ngào", [(rose["id"], 5), (baby["id"], 3)])

    assert tpl["slug"] == "pastel-ngot-ngao"
    assert tpl["price"] == 450_000
    assert {(i["flower_type"]["name"], i["quantity"]) for i in tpl["items"]} == {
        ("Hồng phấn", 5),
        ("Baby trắng", 3),
    }


async def test_duplicate_names_get_unique_slugs(new_flower, new_template):
    rose = await new_flower("Hồng")
    first = await new_template("Bó Hồng", [(rose["id"], 5)])
    second = await new_template("Bó hồng", [(rose["id"], 7)])
    third = await new_template("Bó  Hồng!", [(rose["id"], 9)])
    assert [first["slug"], second["slug"], third["slug"]] == ["bo-hong", "bo-hong-2", "bo-hong-3"]


async def test_explicit_duplicate_slug_conflicts(client, owner_headers, new_flower, new_template):
    rose = await new_flower("Hồng")
    await new_template("A", [(rose["id"], 1)], slug="bo-dac-biet")
    r = await client.post(
        TPL,
        json={
            "name": "B",
            "slug": "bo-dac-biet",
            "price": 100_000,
            "items": [{"flower_type_id": rose["id"], "quantity": 1}],
        },
        headers=owner_headers,
    )
    assert r.status_code == 409


@pytest.mark.parametrize(
    ("items", "expected_status", "expected_code"),
    [
        ([], 422, None),
        ([{"flower_type_id": "ROSE", "quantity": 0}], 422, None),
        (
            [{"flower_type_id": "ROSE", "quantity": 1}, {"flower_type_id": "ROSE", "quantity": 2}],
            422,
            None,
        ),
        ([{"flower_type_id": 99999, "quantity": 1}], 400, "UNKNOWN_FLOWER_TYPE"),
    ],
    ids=["empty", "zero-quantity", "duplicate-flower", "unknown-flower"],
)
async def test_invalid_recipes(
    client, owner_headers, new_flower, items, expected_status, expected_code
):
    rose = await new_flower("Hồng")
    for item in items:
        if item["flower_type_id"] == "ROSE":
            item["flower_type_id"] = rose["id"]
    r = await client.post(
        TPL, json={"name": "X", "price": 100_000, "items": items}, headers=owner_headers
    )
    assert r.status_code == expected_status, r.text
    if expected_code:
        assert r.json()["code"] == expected_code


async def test_recipe_cannot_use_inactive_flower(client, owner_headers, new_flower):
    old = await new_flower("Hoa cũ")
    await client.patch(f"{FT}/{old['id']}", json={"is_active": False}, headers=owner_headers)
    r = await client.post(
        TPL,
        json={"name": "X", "price": 1, "items": [{"flower_type_id": old["id"], "quantity": 1}]},
        headers=owner_headers,
    )
    assert r.status_code == 400
    assert r.json()["code"] == "INACTIVE_FLOWER_TYPE"


async def test_price_change_is_recorded_in_history(client, owner_headers, new_flower, new_template):
    rose = await new_flower("Hồng")
    tpl = await new_template("Đỏ Rực", [(rose["id"], 10)], price=500_000)
    url = f"{TPL}/{tpl['id']}"

    await client.patch(url, json={"price": 550_000}, headers=owner_headers)
    await client.patch(
        url, json={"price": 550_000}, headers=owner_headers
    )  # không đổi -> không ghi
    await client.patch(url, json={"description": "Mới"}, headers=owner_headers)  # không phải giá
    await client.patch(url, json={"price": 520_000}, headers=owner_headers)

    r = await client.get(f"{url}/price-history", headers=owner_headers)
    assert r.status_code == 200
    assert [(h["old_price"], h["new_price"]) for h in r.json()] == [
        (550_000, 520_000),
        (500_000, 550_000),
    ]
    assert all(h["changed_by_id"] is not None for h in r.json())


async def test_replace_recipe(client, owner_headers, new_flower, new_template):
    rose = await new_flower("Hồng")
    baby = await new_flower("Baby")
    leaf = await new_flower("Lá bạch đàn", color="xanh")
    tpl = await new_template("Mix", [(rose["id"], 5), (baby["id"], 3)])

    r = await client.put(
        f"{TPL}/{tpl['id']}/items",
        json={
            "items": [
                {"flower_type_id": rose["id"], "quantity": 7},
                {"flower_type_id": leaf["id"], "quantity": 4},
            ]
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert {(i["flower_type"]["id"], i["quantity"]) for i in r.json()["items"]} == {
        (rose["id"], 7),
        (leaf["id"], 4),
    }


async def test_unknown_template_returns_404(client, owner_headers):
    r = await client.patch(f"{TPL}/9999", json={"price": 1}, headers=owner_headers)
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"

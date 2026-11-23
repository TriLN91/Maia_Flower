import pytest

SHOP = "/api/v1/shop/templates"


@pytest.fixture
async def catalog(client, owner_headers):
    """3 mẫu đang bán + 1 mẫu đã tắt."""
    r = await client.post(
        "/api/v1/admin/flower-types",
        json={"name": "Hồng", "color": "đỏ", "vase_life_days": 7, "reference_cost": 9000},
        headers=owner_headers,
    )
    rose_id = r.json()["id"]

    created = {}
    for name, price in [("Bó Nhỏ Xinh", 250_000), ("Pastel", 450_000), ("Sang Trọng", 900_000)]:
        r = await client.post(
            "/api/v1/admin/templates",
            json={
                "name": name,
                "price": price,
                "items": [{"flower_type_id": rose_id, "quantity": 5}],
            },
            headers=owner_headers,
        )
        created[name] = r.json()

    r = await client.post(
        "/api/v1/admin/templates",
        json={
            "name": "Ngừng bán",
            "price": 300_000,
            "items": [{"flower_type_id": rose_id, "quantity": 3}],
        },
        headers=owner_headers,
    )
    hidden = r.json()
    await client.patch(
        f"/api/v1/admin/templates/{hidden['id']}", json={"is_active": False}, headers=owner_headers
    )
    created["hidden"] = hidden
    return created


async def test_public_list_without_login_hides_inactive(client, catalog):
    r = await client.get(SHOP)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert [t["name"] for t in body["items"]] == ["Bó Nhỏ Xinh", "Pastel", "Sang Trọng"]


async def test_public_payload_does_not_leak_internal_fields(client, catalog):
    item = (await client.get(SHOP)).json()["items"][0]
    for internal in ("is_active", "discount_locked", "updated_by_id", "reference_cost"):
        assert internal not in item
    assert "reference_cost" not in item["items"][0]["flower_type"]


async def test_filter_sort_and_paginate(client, catalog):
    r = await client.get(SHOP, params={"min_price": 300_000, "sort": "price_desc"})
    assert [t["name"] for t in r.json()["items"]] == ["Sang Trọng", "Pastel"]

    page1 = (await client.get(SHOP, params={"limit": 2, "sort": "price_asc"})).json()
    page2 = (await client.get(SHOP, params={"limit": 2, "offset": 2, "sort": "price_asc"})).json()
    assert page1["total"] == page2["total"] == 3
    assert [t["price"] for t in page1["items"] + page2["items"]] == [250_000, 450_000, 900_000]


async def test_invalid_price_range(client, catalog):
    r = await client.get(SHOP, params={"min_price": 500_000, "max_price": 100_000})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_PRICE_RANGE"


async def test_get_by_slug(client, catalog):
    r = await client.get(f"{SHOP}/pastel")
    assert r.status_code == 200
    assert r.json()["price"] == 450_000


async def test_inactive_template_is_not_found_by_slug(client, catalog):
    r = await client.get(f"{SHOP}/{catalog['hidden']['slug']}")
    assert r.status_code == 404

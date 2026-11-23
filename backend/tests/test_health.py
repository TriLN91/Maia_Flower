async def test_health_reports_all_components_ok(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"api": "ok", "database": "ok", "redis": "ok"}

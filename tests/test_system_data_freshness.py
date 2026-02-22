def test_system_data_freshness_endpoint(client):
    r = client.get("/api/system/data-freshness")
    assert r.status_code == 200
    data = r.json()
    assert "sources" in data
    assert "source_count" in data
    assert "stale_count" in data
    assert data["source_count"] >= 1


def test_system_data_freshness_source_shape(client):
    r = client.get("/api/system/data-freshness")
    assert r.status_code == 200
    src = r.json()["sources"][0]
    assert "source_name" in src
    assert "latest_record_date" in src
    assert "table_name" in src
    assert "row_count" in src
    assert "last_refreshed" in src
    assert "stale" in src


def test_system_data_freshness_stale_count_consistency(client):
    r = client.get("/api/system/data-freshness")
    assert r.status_code == 200
    data = r.json()
    computed = sum(1 for s in data["sources"] if s["stale"])
    assert computed == data["stale_count"]

from beli_tool.places_cache import PlacesCache


def test_put_then_get_roundtrips():
    c = PlacesCache(":memory:")
    c.put("k", [{"place_id": "p1", "name": "Lilia"}])
    assert c.get("k") == [{"place_id": "p1", "name": "Lilia"}]


def test_miss_returns_none():
    assert PlacesCache(":memory:").get("nope") is None


def test_empty_response_is_a_hit_not_a_miss():
    # The whole point: a place that matched nothing must not be re-billed
    # on every run. [] is a real cached answer, distinct from None (a miss).
    c = PlacesCache(":memory:")
    c.put("k", [])
    assert c.get("k") == []
    assert c.get("k") is not None


def test_expired_entry_is_a_miss():
    c = PlacesCache(":memory:", ttl_days=30)
    c.put("k", [{"place_id": "p1"}])
    # Age the row past the TTL; restaurants close, so stale entries re-query.
    with c._lock:
        c.conn.execute("UPDATE places_cache SET ts = datetime('now', '-31 days')")
        c.conn.commit()
    assert c.get("k") is None


def test_put_overwrites_existing_key():
    c = PlacesCache(":memory:")
    c.put("k", [{"name": "old"}])
    c.put("k", [{"name": "new"}])
    assert c.get("k") == [{"name": "new"}]


def test_cache_persists_across_instances(tmp_path):
    db = tmp_path / "l.sqlite"
    PlacesCache(db).put("k", [{"name": "Lilia"}])
    assert PlacesCache(db).get("k") == [{"name": "Lilia"}]  # survives a restart

import httpx

from beli_tool.config import Config
from beli_tool.cli import build_app_from_config, local_ip
from beli_tool.places_cache import PlacesCache
from beli_tool.places_client import PlacesClient


class FakeSource:
    def points(self):
        return []


class FakeClient:
    def text_search(self, query):
        return [{"place_id": "w1", "name": query, "formatted_address": "x", "types": ["restaurant"]}]

    def nearby_food(self, lat, lon, radius_m=60):
        return []


def test_local_ip_returns_string():
    assert isinstance(local_ip(), str)


def test_build_app_from_config_wires_sources(tmp_path):
    (tmp_path / "Want to go.csv").write_text("Title,Note,URL\nDhamaka,,u\n")
    cfg = Config(api_key="k", saved_dir=tmp_path, db_path=tmp_path / "l.sqlite")
    app, ledger = build_app_from_config(cfg, photo_source=FakeSource(), client=FakeClient())
    from fastapi.testclient import TestClient
    data = TestClient(app).get("/api/queue").json()
    assert [i["name"] for i in data["want_to_try"]] == ["Dhamaka"]


class ThreeVisitSource:
    """Three GPS points far apart in space and a month apart in time → 3 visits."""

    def points(self):
        from datetime import datetime
        from beli_tool.clustering import PhotoPoint
        return [
            PhotoPoint("a", 40.0, -73.0, datetime(2026, 1, 1, 12, 0)),
            PhotoPoint("b", 41.0, -74.0, datetime(2026, 2, 1, 12, 0)),
            PhotoPoint("c", 42.0, -75.0, datetime(2026, 3, 1, 12, 0)),
        ]


class AnyFoodClient:
    def text_search(self, query):
        return []

    def nearby_food(self, lat, lon, radius_m=60):
        return [{"place_id": f"{lat},{lon}", "name": "R", "vicinity": "x",
                 "types": ["restaurant"],
                 "geometry": {"location": {"lat": lat, "lng": lon}}}]


def test_build_app_gives_the_places_client_a_cache(tmp_path):
    # Guards the wiring itself: without a cache on the real client, every other
    # test still passes and she still gets billed on every run.
    seen = {}

    class SpyClient:
        def __init__(self, api_key, cache=None):
            seen["cache"] = cache

        def text_search(self, query):
            return []

        def nearby_food(self, lat, lon, radius_m=60):
            return []

    import beli_tool.cli as cli_mod

    original = cli_mod.PlacesClient
    cli_mod.PlacesClient = SpyClient
    try:
        cfg = Config(api_key="k", saved_dir=tmp_path, db_path=tmp_path / "l.sqlite")
        build_app_from_config(cfg, photo_source=FakeSource())
    finally:
        cli_mod.PlacesClient = original
    assert isinstance(seen["cache"], PlacesCache)


def test_second_run_is_fully_cached_and_bills_nothing(tmp_path):
    (tmp_path / "Want to go.csv").write_text("Title,Note,URL\nDhamaka,,u\n")
    db = tmp_path / "l.sqlite"
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"places": [
            {"id": "w1", "displayName": {"text": "Dhamaka"},
             "formattedAddress": "119 Delancey", "types": ["restaurant"]},
        ]})

    def fresh_client():  # a new client each run, sharing the on-disk cache
        return PlacesClient(
            "k",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            cache=PlacesCache(db),
        )

    cfg = Config(api_key="k", saved_dir=tmp_path, db_path=db)
    build_app_from_config(cfg, photo_source=FakeSource(), client=fresh_client())
    assert calls["n"] == 1
    build_app_from_config(cfg, photo_source=FakeSource(), client=fresh_client())
    assert calls["n"] == 1  # second run answered entirely from cache


def test_build_app_caps_visits_to_max(tmp_path):
    cfg = Config(api_key="k", saved_dir=tmp_path, db_path=tmp_path / "l.sqlite", max_visits=1)
    app, _ = build_app_from_config(cfg, photo_source=ThreeVisitSource(), client=AnyFoodClient())
    from fastapi.testclient import TestClient
    data = TestClient(app).get("/api/queue").json()
    # 3 visits exist but the cap keeps only the single most-recent one
    assert len(data["been"]) == 1

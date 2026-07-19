from urllib.parse import unquote_plus

import httpx
import pytest

from beli_tool.osm_client import OsmClient
from beli_tool.places_client import PlacesError
from beli_tool.places_cache import PlacesCache


def _client(handler, cache=None):
    return OsmClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache=cache,
        min_interval_s=0,  # tests must not sit out the fair-use pacing
    )


def test_nearby_food_queries_overpass_and_normalizes():
    def handler(request):
        assert "overpass" in request.url.host
        body = unquote_plus(request.read().decode())
        assert "around:60" in body
        assert "amenity" in body
        return httpx.Response(200, json={"elements": [
            {"type": "node", "id": 42, "lat": 40.7184, "lon": -73.9568,
             "tags": {"name": "Lilia", "amenity": "restaurant",
                      "addr:housenumber": "567", "addr:street": "Union Ave"}},
        ]})

    r = _client(handler).nearby_food(40.7184, -73.9568)[0]
    assert r["place_id"] == "osm:node/42"
    assert r["name"] == "Lilia"
    assert r["vicinity"] == "567 Union Ave"
    assert "restaurant" in r["types"]
    assert r["geometry"]["location"]["lat"] == 40.7184
    assert r["geometry"]["location"]["lng"] == -73.9568


def test_nearby_food_maps_osm_tags_and_uses_way_center():
    def handler(request):
        return httpx.Response(200, json={"elements": [
            {"type": "way", "id": 7, "center": {"lat": 1.0, "lon": 2.0},
             "tags": {"name": "Shake Shack", "amenity": "fast_food"}},
            {"type": "node", "id": 8, "lat": 1.0, "lon": 2.0,
             "tags": {"amenity": "restaurant"}},  # unnamed: dropped
        ]})

    results = _client(handler).nearby_food(1.0, 2.0)
    assert len(results) == 1
    r = results[0]
    assert r["place_id"] == "osm:way/7"
    assert r["types"] == ["meal_takeaway"]  # matcher's vocabulary, not OSM's
    assert r["geometry"]["location"]["lat"] == 1.0


def test_text_search_queries_nominatim_and_normalizes():
    def handler(request):
        assert "nominatim" in request.url.host
        assert request.url.params["q"] == "Dhamaka"
        assert request.url.params["format"] == "jsonv2"
        return httpx.Response(200, json=[
            {"osm_type": "node", "osm_id": 99, "lat": "40.718", "lon": "-73.988",
             "name": "Dhamaka", "type": "restaurant",
             "display_name": "Dhamaka, 119 Delancey Street, New York"},
        ])

    r = _client(handler).text_search("Dhamaka")[0]
    assert r["place_id"] == "osm:node/99"
    assert r["name"] == "Dhamaka"
    assert r["formatted_address"] == "119 Delancey Street, New York"
    assert r["types"] == ["restaurant"]
    assert r["geometry"]["location"]["lat"] == 40.718


def test_non_food_nominatim_hit_keeps_raw_type():
    # A park must not be dressed up as food; the matcher filters it out.
    def handler(request):
        return httpx.Response(200, json=[
            {"osm_type": "way", "osm_id": 5, "lat": "1", "lon": "2",
             "name": "McCarren Park", "type": "park",
             "display_name": "McCarren Park, Brooklyn"},
        ])

    assert _client(handler).text_search("McCarren Park")[0]["types"] == ["park"]


def test_cache_short_circuits_second_lookup():
    seen = {"n": 0}

    def handler(request):
        seen["n"] += 1
        return httpx.Response(200, json={"elements": []})

    c = _client(handler, cache=PlacesCache())
    assert c.nearby_food(1.0, 2.0) == []
    assert c.nearby_food(1.0, 2.0) == []  # served from cache, even though empty
    assert seen["n"] == 1
    assert (c.calls, c.hits) == (1, 1)


def test_retries_transient_failures_then_succeeds(monkeypatch):
    monkeypatch.setattr("beli_tool.osm_client._retry_delay", lambda r, a: 0)
    seen = {"n": 0}

    def handler(request):
        seen["n"] += 1
        if seen["n"] < 3:
            return httpx.Response(504)
        return httpx.Response(200, json={"elements": []})

    assert _client(handler).nearby_food(1.0, 2.0) == []
    assert seen["n"] == 3


def test_rotates_to_mirror_on_server_error(monkeypatch):
    monkeypatch.setattr("beli_tool.osm_client._retry_delay", lambda r, a: 0)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if len(hosts) == 1:
            return httpx.Response(504)
        return httpx.Response(200, json={"elements": []})

    assert _client(handler).nearby_food(1.0, 2.0) == []
    assert hosts[0] != hosts[1]  # second attempt went to the other mirror


def test_sustained_server_errors_raise_actionable_message(monkeypatch):
    monkeypatch.setattr("beli_tool.osm_client._retry_delay", lambda r, a: 0)

    def handler(request):
        return httpx.Response(504)

    with pytest.raises(PlacesError, match="rerun in a few minutes"):
        _client(handler).nearby_food(1.0, 2.0)

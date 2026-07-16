import httpx
import pytest

from beli_tool.places_cache import PlacesCache
from beli_tool.places_client import PlacesClient, PlacesError


def _client(handler, cache=None):
    return PlacesClient(
        "KEY", client=httpx.Client(transport=httpx.MockTransport(handler)), cache=cache
    )


def _ok(request):
    return httpx.Response(200, json={"places": [
        {"id": "p1", "displayName": {"text": "Lilia"},
         "formattedAddress": "567 Union Ave", "types": ["restaurant"]},
    ]})


def test_text_search_hits_new_endpoint_and_normalizes():
    def handler(request):
        assert request.url.path.endswith("/places:searchText")
        assert request.headers["X-Goog-Api-Key"] == "KEY"
        assert "X-Goog-FieldMask" in request.headers
        return httpx.Response(200, json={"places": [
            {"id": "p1", "displayName": {"text": "Dhamaka"},
             "formattedAddress": "119 Delancey St", "types": ["restaurant", "food"]},
        ]})

    results = _client(handler).text_search("Dhamaka")
    top = results[0]
    assert top["place_id"] == "p1"
    assert top["name"] == "Dhamaka"
    assert top["formatted_address"] == "119 Delancey St"
    assert "restaurant" in top["types"]


def test_nearby_food_hits_new_endpoint_and_normalizes_location():
    def handler(request):
        assert request.url.path.endswith("/places:searchNearby")
        assert request.headers["X-Goog-Api-Key"] == "KEY"
        return httpx.Response(200, json={"places": [
            {"id": "b1", "displayName": {"text": "Lilia"},
             "formattedAddress": "567 Union Ave", "types": ["restaurant"],
             "location": {"latitude": 40.7184, "longitude": -73.9568}},
        ]})

    results = _client(handler).nearby_food(40.7184, -73.9568)
    r = results[0]
    assert r["place_id"] == "b1"
    assert r["name"] == "Lilia"
    assert r["vicinity"] == "567 Union Ave"
    assert r["geometry"]["location"]["lat"] == 40.7184
    assert r["geometry"]["location"]["lng"] == -73.9568


def test_empty_places_returns_empty_list():
    def handler(request):
        return httpx.Response(200, json={})

    assert _client(handler).text_search("nowhere") == []


def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("beli_tool.places_client.time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json={"places": [
            {"id": "p1", "displayName": {"text": "Lilia"},
             "formattedAddress": "x", "types": ["restaurant"]},
        ]})

    results = _client(handler).text_search("Lilia")
    assert calls["n"] == 2  # one 429, one success
    assert results[0]["place_id"] == "p1"


def test_403_becomes_an_actionable_message_not_a_traceback():
    def handler(request):
        return httpx.Response(403, json={"error": {"message": "Places API has not been used in project 123"}})

    with pytest.raises(PlacesError) as e:
        _client(handler).text_search("Lilia")
    msg = str(e.value)
    assert "billing" in msg  # names the usual causes
    assert "Places API has not been used in project 123" in msg  # and quotes Google


def test_429_after_retries_becomes_a_quota_message(monkeypatch):
    monkeypatch.setattr("beli_tool.places_client.time.sleep", lambda s: None)

    def handler(request):
        return httpx.Response(429, json={})

    with pytest.raises(PlacesError) as e:
        _client(handler).nearby_food(40.0, -73.0)
    assert "quota" in str(e.value)


def test_500_still_raises_the_raw_http_error(monkeypatch):
    # Not a setup mistake — don't dress a server fault up as one.
    monkeypatch.setattr("beli_tool.places_client.time.sleep", lambda s: None)

    def handler(request):
        return httpx.Response(503, json={})

    with pytest.raises(httpx.HTTPStatusError):
        _client(handler).text_search("Lilia")


def test_cache_prevents_a_second_billed_call():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _ok(request)

    cache = PlacesCache(":memory:")
    c1 = _client(handler, cache=cache)
    assert c1.text_search("Lilia")[0]["place_id"] == "p1"
    # A fresh client sharing the cache (i.e. the next run) must not re-bill.
    c2 = _client(handler, cache=cache)
    assert c2.text_search("Lilia")[0]["place_id"] == "p1"
    assert calls["n"] == 1
    assert (c1.calls, c1.hits) == (1, 0)
    assert (c2.calls, c2.hits) == (0, 1)


def test_cache_keys_on_the_exact_request_not_just_the_endpoint():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _ok(request)

    c = _client(handler, cache=PlacesCache(":memory:"))
    c.text_search("Lilia")
    c.text_search("Dhamaka")  # different query → different key → real call
    c.text_search("Lilia")  # repeat → hit
    assert calls["n"] == 2
    assert (c.calls, c.hits) == (2, 1)


def test_cached_empty_result_is_not_re_billed():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={})

    c = _client(handler, cache=PlacesCache(":memory:"))
    assert c.text_search("nowhere") == []
    assert c.text_search("nowhere") == []
    assert calls["n"] == 1  # the no-match case is the one that used to re-bill


def test_nearby_and_text_share_a_cache_without_colliding():
    def handler(request):
        return _ok(request)

    c = _client(handler, cache=PlacesCache(":memory:"))
    c.text_search("Lilia")
    c.nearby_food(40.0, -73.0)
    assert c.calls == 2  # same cache, different endpoints → no false hit
    assert c.hits == 0

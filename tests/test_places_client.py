import httpx

from beli_tool.places_client import PlacesClient


def _client(handler):
    return PlacesClient("KEY", client=httpx.Client(transport=httpx.MockTransport(handler)))


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

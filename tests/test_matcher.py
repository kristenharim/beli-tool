from datetime import date
from beli_tool.models import RawPlace
from beli_tool.matcher import match_maps_place, match_photo_cluster


class FakeClient:
    def __init__(self, text=None, nearby=None):
        self._text = text or []
        self._nearby = nearby or []

    def text_search(self, query):
        return self._text

    def nearby_food(self, lat, lon, radius_m=60):
        return self._nearby


def test_match_maps_confident():
    client = FakeClient(text=[
        {"place_id": "p1", "name": "Dhamaka", "formatted_address": "119 Delancey St",
         "types": ["restaurant", "food"]},
    ])
    m = match_maps_place(RawPlace(source="maps", name="Dhamaka"), client)
    assert m.status == "confident" and m.bucket == "want_to_try"
    assert m.match.place_id == "p1"


def test_match_maps_no_results():
    m = match_maps_place(RawPlace(source="maps", name="Nowhere"), FakeClient(text=[]))
    assert m.status == "no_match" and m.match is None


def test_match_photo_confident_single():
    nearby = [
        {"place_id": "p1", "name": "Lilia", "vicinity": "567 Union Ave",
         "types": ["restaurant"], "geometry": {"location": {"lat": 40.7184, "lng": -73.9568}}},
    ]
    raw = RawPlace(source="photos", lat=40.7184, lon=-73.9568, visit_date=date(2026, 4, 12))
    m = match_photo_cluster(raw, FakeClient(nearby=nearby))
    assert m.status == "confident" and m.bucket == "been"
    assert m.match.name == "Lilia"


def test_match_photo_ambiguous_two_close():
    nearby = [
        {"place_id": "p1", "name": "Los Tacos No. 1", "vicinity": "75 9th Ave",
         "types": ["restaurant"], "geometry": {"location": {"lat": 40.7220, "lng": -73.9876}}},
        {"place_id": "p2", "name": "Time Out Market", "vicinity": "55 Water St",
         "types": ["restaurant"], "geometry": {"location": {"lat": 40.72205, "lng": -73.98762}}},
    ]
    raw = RawPlace(source="photos", lat=40.7220, lon=-73.9876)
    m = match_photo_cluster(raw, FakeClient(nearby=nearby))
    assert m.status == "ambiguous"
    assert {c.place_id for c in m.candidates} == {"p1", "p2"}
    assert m.match is None


def test_match_photo_no_food_nearby():
    raw = RawPlace(source="photos", lat=40.0, lon=-73.0)
    client = FakeClient(nearby=[
        {"place_id": "p9", "name": "Some Park", "vicinity": "x",
         "types": ["park"], "geometry": {"location": {"lat": 40.0, "lng": -73.0}}}])
    m = match_photo_cluster(raw, client)
    assert m.status == "no_match" and m.bucket == "been" and m.match is None

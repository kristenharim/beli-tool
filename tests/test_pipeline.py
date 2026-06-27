from datetime import date
from beli_tool.models import RawPlace
from beli_tool.ledger import Ledger
from beli_tool.pipeline import build_queue


class FakeClient:
    def text_search(self, query):
        return [{"place_id": "w1", "name": query, "formatted_address": "x",
                 "types": ["restaurant"]}]

    def nearby_food(self, lat, lon, radius_m=60):
        return [{"place_id": "b1", "name": "Lilia", "vicinity": "567 Union Ave",
                 "types": ["restaurant"],
                 "geometry": {"location": {"lat": lat, "lng": lon}}}]


def test_build_queue_sorts_and_dedupes():
    maps = [RawPlace(source="maps", name="Dhamaka")]
    photos = [RawPlace(source="photos", lat=40.7, lon=-73.9, visit_date=date(2026, 4, 12))]
    led = Ledger(":memory:")
    q = build_queue(maps, photos, FakeClient(), led)
    assert [m.match.name for m in q.want_to_try] == ["Dhamaka"]
    assert [m.match.name for m in q.been] == ["Lilia"]

    # mark the photo place handled -> disappears next build
    led.mark_added("b1", "Lilia", "been", "loved")
    q2 = build_queue(maps, photos, FakeClient(), led)
    assert q2.been == []
    assert [m.match.name for m in q2.want_to_try] == ["Dhamaka"]

from datetime import datetime
from beli_tool.clustering import PhotoPoint
from beli_tool.photos_collector import collect_photos


class StubSource:
    def __init__(self, pts):
        self._pts = pts

    def points(self):
        return self._pts


def test_collect_photos_makes_one_rawplace_per_cluster():
    src = StubSource([
        PhotoPoint("a", 40.7184, -73.9568, datetime(2026, 4, 12, 19, 0)),
        PhotoPoint("b", 40.7184, -73.9569, datetime(2026, 4, 12, 19, 10)),
        PhotoPoint("c", 40.7220, -73.9876, datetime(2026, 3, 3, 13, 0)),
    ])
    raws = collect_photos(src)
    assert len(raws) == 2
    assert all(r.source == "photos" for r in raws)
    dinner = [r for r in raws if r.photo_count == 2][0]
    assert dinner.visit_date.isoformat() == "2026-04-12"
    assert dinner.photo_ref == "a"  # representative = earliest
    assert dinner.photo_refs == ["a", "b"]  # full gallery, chronological

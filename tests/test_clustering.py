from datetime import datetime
from beli_tool.clustering import PhotoPoint, cluster_photos, haversine_m


def test_haversine_known_distance():
    # ~111.2 m per 0.001 deg latitude near the equator-ish; assert order of magnitude
    d = haversine_m(40.7180, -73.9568, 40.7184, -73.9568)
    assert 30 < d < 60


def test_two_visits_split_by_distance():
    pts = [
        PhotoPoint("a", 40.7184, -73.9568, datetime(2026, 4, 12, 19, 0)),
        PhotoPoint("b", 40.7184, -73.9569, datetime(2026, 4, 12, 19, 10)),
        PhotoPoint("c", 40.7220, -73.9876, datetime(2026, 4, 12, 19, 5)),
    ]
    clusters = cluster_photos(pts)
    assert len(clusters) == 2
    counts = sorted(c.count for c in clusters)
    assert counts == [1, 2]


def test_same_place_different_day_splits_by_time():
    pts = [
        PhotoPoint("a", 40.7184, -73.9568, datetime(2026, 4, 12, 19, 0)),
        PhotoPoint("b", 40.7184, -73.9568, datetime(2026, 4, 20, 19, 0)),
    ]
    assert len(cluster_photos(pts)) == 2

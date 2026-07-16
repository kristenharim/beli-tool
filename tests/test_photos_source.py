from datetime import date, datetime

from beli_tool.photos_source import OsxPhotosSource


class FakePhoto:
    def __init__(self, uuid, lat, lon, taken):
        self.uuid = uuid
        self.location = (lat, lon)
        self.date = taken


class FakeDB:
    """Records the kwargs points() passes down to osxphotos."""

    def __init__(self, photos):
        self._photos = photos
        self.seen_kwargs = None

    def photos(self, **kwargs):
        self.seen_kwargs = kwargs
        return self._photos


def _source_with(photos, **kw):
    src = OsxPhotosSource(**kw)
    db = FakeDB(photos)
    src._db = db  # skip the real library open
    return src, db


def test_since_is_pushed_down_to_osxphotos():
    # Filtering in osxphotos, not after — that's what bounds the scan.
    src, db = _source_with([], since=date(2024, 1, 1))
    src.points()
    assert db.seen_kwargs["from_date"] == datetime(2024, 1, 1, 0, 0)


def test_no_since_scans_whole_library():
    src, db = _source_with([])
    src.points()
    assert db.seen_kwargs == {}


def test_points_keeps_only_gps_stamped_dated_photos():
    photos = [
        FakePhoto("a", 40.0, -73.0, datetime(2026, 1, 1)),
        FakePhoto("b", None, None, datetime(2026, 1, 2)),  # no GPS
        FakePhoto("c", 41.0, -74.0, None),  # no date
    ]
    src, _ = _source_with(photos)
    assert [p.id for p in src.points()] == ["a"]


def test_progress_callback_fires_during_scan():
    photos = [FakePhoto(str(i), 40.0, -73.0, datetime(2026, 1, 1)) for i in range(1000)]
    seen = []
    src, _ = _source_with(photos, on_progress=seen.append)
    src.points()
    assert seen == [500, 1000]


def test_thumbnail_path_unknown_uuid_returns_none_without_opening_library():
    # _by_uuid is empty until points() runs; an unknown uuid must not touch osxphotos.
    src = OsxPhotosSource()
    assert src.thumbnail_path("does-not-exist") is None


def test_probe_returns_error_string_when_library_unopenable(monkeypatch):
    src = OsxPhotosSource()

    def boom():
        raise RuntimeError("Operation not permitted")

    monkeypatch.setattr(src, "_get_db", boom)
    assert "not permitted" in src.probe()


def test_probe_returns_none_when_library_opens(monkeypatch):
    src = OsxPhotosSource()
    monkeypatch.setattr(src, "_get_db", lambda: object())
    assert src.probe() is None

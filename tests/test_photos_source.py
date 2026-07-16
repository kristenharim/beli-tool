from beli_tool.photos_source import OsxPhotosSource


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

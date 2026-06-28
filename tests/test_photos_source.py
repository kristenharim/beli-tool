from beli_tool.photos_source import OsxPhotosSource


def test_thumbnail_path_unknown_uuid_returns_none_without_opening_library():
    # _by_uuid is empty until points() runs; an unknown uuid must not touch osxphotos.
    src = OsxPhotosSource()
    assert src.thumbnail_path("does-not-exist") is None

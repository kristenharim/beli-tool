from __future__ import annotations

from typing import Protocol

from beli_tool.clustering import PhotoPoint


class PhotoSource(Protocol):
    def points(self) -> list[PhotoPoint]: ...


class OsxPhotosSource:
    """Reads the local Apple Photos library; keeps only GPS-stamped, dated photos."""

    def points(self) -> list[PhotoPoint]:
        import osxphotos

        db = osxphotos.PhotosDB()
        out: list[PhotoPoint] = []
        for p in db.photos():
            loc = p.location  # (lat, lon) or (None, None)
            if loc and loc[0] is not None and loc[1] is not None and p.date:
                out.append(PhotoPoint(id=p.uuid, lat=loc[0], lon=loc[1], taken=p.date))
        return out

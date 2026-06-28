from __future__ import annotations

import os
from typing import Protocol

from beli_tool.clustering import PhotoPoint


class PhotoSource(Protocol):
    def points(self) -> list[PhotoPoint]: ...


class OsxPhotosSource:
    """Reads the local Apple Photos library; keeps only GPS-stamped, dated photos.

    The Photos database is opened once and reused, and the matched photos are
    indexed by UUID so ``thumbnail_path`` can resolve a card's image to a
    browser-displayable derivative without re-reading the library per request.
    """

    def __init__(self) -> None:
        self._db = None
        self._by_uuid: dict = {}

    def _get_db(self):
        if self._db is None:
            import osxphotos

            self._db = osxphotos.PhotosDB()
        return self._db

    def points(self) -> list[PhotoPoint]:
        db = self._get_db()
        out: list[PhotoPoint] = []
        for p in db.photos():
            loc = p.location  # (lat, lon) or (None, None)
            if loc and loc[0] is not None and loc[1] is not None and p.date:
                self._by_uuid[p.uuid] = p
                out.append(PhotoPoint(id=p.uuid, lat=loc[0], lon=loc[1], taken=p.date))
        return out

    def thumbnail_path(self, uuid: str) -> str | None:
        """Resolve a photo UUID to a small, browser-displayable image file.

        Prefers a JPEG derivative (the originals are often HEIC, which browsers
        can't show); falls back to the original. Returns None if unknown.
        """
        p = self._by_uuid.get(uuid)
        if p is None:
            return None
        derivatives = [d for d in (p.path_derivatives or []) if d and os.path.exists(d)]
        if derivatives:
            return min(derivatives, key=os.path.getsize)
        if p.path and os.path.exists(p.path):
            return p.path
        return None

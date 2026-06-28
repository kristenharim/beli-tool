from __future__ import annotations

from beli_tool.clustering import cluster_photos
from beli_tool.models import RawPlace
from beli_tool.photos_source import PhotoSource

# Photos per visit surfaced to the gallery (the full count still shows on the badge).
_GALLERY_CAP = 6


def collect_photos(
    source: PhotoSource, radius_m: float = 75.0, time_gap_hours: float = 6.0
) -> list[RawPlace]:
    clusters = cluster_photos(source.points(), radius_m, time_gap_hours)
    raws: list[RawPlace] = []
    for c in clusters:
        refs = [p.id for p in c.points]  # chronological (points are time-sorted)
        raws.append(
            RawPlace(
                source="photos",
                lat=c.lat,
                lon=c.lon,
                visit_date=c.earliest.date(),
                photo_count=c.count,
                photo_ref=refs[0],
                photo_refs=refs[:_GALLERY_CAP],
            )
        )
    return raws

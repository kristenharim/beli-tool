from __future__ import annotations

from beli_tool.clustering import cluster_photos
from beli_tool.models import RawPlace
from beli_tool.photos_source import PhotoSource


def collect_photos(
    source: PhotoSource, radius_m: float = 75.0, time_gap_hours: float = 6.0
) -> list[RawPlace]:
    clusters = cluster_photos(source.points(), radius_m, time_gap_hours)
    raws: list[RawPlace] = []
    for c in clusters:
        raws.append(
            RawPlace(
                source="photos",
                lat=c.lat,
                lon=c.lon,
                visit_date=c.earliest.date(),
                photo_count=c.count,
                photo_ref=c.points[0].id,
            )
        )
    return raws

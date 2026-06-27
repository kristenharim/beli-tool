from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

EARTH_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = (
        0.5
        - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    )
    return 2 * EARTH_M * math.asin(math.sqrt(a))


@dataclass
class PhotoPoint:
    id: str
    lat: float
    lon: float
    taken: datetime


@dataclass
class Cluster:
    points: list[PhotoPoint] = field(default_factory=list)

    @property
    def lat(self) -> float:
        return sum(p.lat for p in self.points) / len(self.points)

    @property
    def lon(self) -> float:
        return sum(p.lon for p in self.points) / len(self.points)

    @property
    def count(self) -> int:
        return len(self.points)

    @property
    def earliest(self) -> datetime:
        return min(p.taken for p in self.points)


def cluster_photos(
    points: list[PhotoPoint], radius_m: float = 75.0, time_gap_hours: float = 6.0
) -> list[Cluster]:
    clusters: list[Cluster] = []
    for pt in sorted(points, key=lambda p: p.taken):
        placed = False
        for c in clusters:
            within_space = haversine_m(pt.lat, pt.lon, c.lat, c.lon) <= radius_m
            # input is time-sorted, so c.points[-1] is the cluster's most recent
            # point; abs() is defensive against any future unsorted caller
            within_time = (
                abs((pt.taken - c.points[-1].taken).total_seconds())
                <= time_gap_hours * 3600
            )
            if within_space and within_time:
                c.points.append(pt)
                placed = True
                break
        if not placed:
            clusters.append(Cluster(points=[pt]))
    return clusters

from __future__ import annotations

from beli_tool.clustering import haversine_m
from beli_tool.models import MatchedPlace, PlaceCandidate, RawPlace

_FOOD_TYPES = {"restaurant", "food", "cafe", "bar", "bakery", "meal_takeaway"}


def _dist(c: PlaceCandidate) -> float:
    return c.distance_m if c.distance_m is not None else 1e9


def match_maps_place(raw: RawPlace, client) -> MatchedPlace:
    results = client.text_search(raw.name or "")
    if not results:
        return MatchedPlace(bucket="want_to_try", status="no_match", raw=raw)
    top = results[0]
    cand = PlaceCandidate(
        place_id=top["place_id"],
        name=top["name"],
        address=top.get("formatted_address", ""),
        category=(top.get("types") or ["unknown"])[0],
    )
    return MatchedPlace(bucket="want_to_try", status="confident", raw=raw, match=cand)


def match_photo_cluster(
    raw: RawPlace, client, ambiguous_radius_m: float = 25.0
) -> MatchedPlace:
    results = client.nearby_food(raw.lat, raw.lon)
    food = [r for r in results if _FOOD_TYPES & set(r.get("types", []))]
    if not food:
        return MatchedPlace(bucket="been", status="no_match", raw=raw)

    cands: list[PlaceCandidate] = []
    for r in food:
        loc = r["geometry"]["location"]
        cands.append(
            PlaceCandidate(
                place_id=r["place_id"],
                name=r["name"],
                address=r.get("vicinity", ""),
                category=(r.get("types") or ["unknown"])[0],
                distance_m=haversine_m(raw.lat, raw.lon, loc["lat"], loc["lng"]),
            )
        )
    cands.sort(key=_dist)

    near = [c for c in cands if _dist(c) <= ambiguous_radius_m]
    if len(near) >= 2:
        return MatchedPlace(bucket="been", status="ambiguous", raw=raw, candidates=near)
    return MatchedPlace(bucket="been", status="confident", raw=raw, match=cands[0])

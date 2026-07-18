from __future__ import annotations

from difflib import SequenceMatcher

from beli_tool.clustering import haversine_m
from beli_tool.models import MatchedPlace, PlaceCandidate, RawPlace

_FOOD_TYPES = {"restaurant", "food", "cafe", "bar", "bakery", "meal_takeaway"}
_NAME_THRESHOLD = 0.6


def _dist(c: PlaceCandidate) -> float:
    return c.distance_m if c.distance_m is not None else 1e9


def _candidate(r: dict, distance_m: float | None = None) -> PlaceCandidate:
    return PlaceCandidate(
        place_id=r["place_id"],
        name=r["name"],
        address=r.get("formatted_address") or r.get("vicinity", ""),
        category=(r.get("types") or ["unknown"])[0],
        distance_m=distance_m,
    )


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum() or c.isspace()).strip()


def _name_matches(query: str, found: str, threshold: float = _NAME_THRESHOLD) -> bool:
    """Does Google's hit actually resemble the name that was saved?

    Guards against text_search confidently returning a same-named place in a
    different city, or an unrelated business entirely.
    """
    q, f = _norm(query), _norm(found)
    if not q or not f:
        return False
    if q in f or f in q:  # "Lilia" vs "Lilia Ristorante"
        return True
    return SequenceMatcher(None, q, f).ratio() >= threshold


def match_maps_place(raw: RawPlace, client) -> MatchedPlace:
    results = client.text_search(raw.name or "")
    food = [r for r in results if _FOOD_TYPES & set(r.get("types", []))]
    if not food:
        # Nothing edible came back (a park, a hotel, or no hit at all). Beli
        # only takes restaurants, so surface it rather than mismatching it.
        return MatchedPlace(bucket="want_to_try", status="no_match", raw=raw)
    cand = _candidate(food[0])
    if not _name_matches(raw.name or "", cand.name):
        # Best food hit doesn't look like what she saved. Don't call that
        # confident; hand it back as a one-tap confirmation instead.
        return MatchedPlace(
            bucket="want_to_try", status="ambiguous", raw=raw, candidates=[cand]
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
            _candidate(r, distance_m=haversine_m(raw.lat, raw.lon, loc["lat"], loc["lng"]))
        )
    cands.sort(key=_dist)

    near = [c for c in cands if _dist(c) <= ambiguous_radius_m]
    if len(near) >= 2:
        return MatchedPlace(bucket="been", status="ambiguous", raw=raw, candidates=near)
    return MatchedPlace(bucket="been", status="confident", raw=raw, match=cands[0])

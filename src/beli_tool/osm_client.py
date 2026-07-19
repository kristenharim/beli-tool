from __future__ import annotations

import json
import time

import httpx

from beli_tool import __version__
from beli_tool.places_client import PlacesError, _retry_delay

# Overpass mirrors, rotated between retries: the main instance throws long
# stretches of 504 under load, and a run of hundreds of lookups will hit one.
_OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
_NOMINATIM = "https://nominatim.openstreetmap.org/search"
# All community-run servers with a roughly 1 request/second fair-use
# policy. Nominatim also requires a real User-Agent naming the app.
_USER_AGENT = f"beli-tool/{__version__} (github.com/kristenharim/beli-tool)"
_MIN_INTERVAL_S = 1.0
_MAX_RETRIES = 8

# OSM tag values mapped into the matcher's type vocabulary (see
# matcher._FOOD_TYPES). Anything unmapped passes through as-is and the
# matcher's food filter rejects it, same as a park or hotel from Google.
_TYPE_MAP = {
    "restaurant": "restaurant",
    "cafe": "cafe",
    "bar": "bar",
    "pub": "bar",
    "biergarten": "bar",
    "fast_food": "meal_takeaway",
    "food_court": "food",
    "ice_cream": "food",
    "bakery": "bakery",
}
_AMENITY_RE = "restaurant|cafe|bar|pub|biergarten|fast_food|food_court|ice_cream"


class OsmClient:
    """Free OpenStreetMap stand-in for PlacesClient.

    Overpass answers the photo-cluster nearby lookups, Nominatim answers the
    saved-list name searches. Both normalize into the exact dict shape
    PlacesClient produces, so matcher.py cannot tell the providers apart.
    No API key, no billing account. The trade: OSM coverage is thinner than
    Google's, so more visits land in the review queue instead of matching
    confidently.

    Takes the same optional cache as PlacesClient; keys are prefixed "osm:"
    so the two providers never collide in one cache file. Requests are paced
    to min_interval_s apart (cache hits skip the wait), and hits/calls mirror
    the PlacesClient counters the CLI reports.
    """

    def __init__(
        self,
        client: httpx.Client | None = None,
        cache=None,
        min_interval_s: float = _MIN_INTERVAL_S,
    ):
        self._http = client or httpx.Client(
            timeout=30.0, headers={"User-Agent": _USER_AGENT}
        )
        self._cache = cache
        self._min_interval_s = min_interval_s
        self._last_call = 0.0
        self.hits = 0
        self.calls = 0

    def text_search(self, query: str) -> list[dict]:
        params = {"q": query, "format": "jsonv2", "limit": 10}
        key = f"osm:search:{json.dumps(params, sort_keys=True)}"
        return self._fetch(
            key,
            lambda attempt: self._http.get(_NOMINATIM, params=params),
            _parse_nominatim,
        )

    def nearby_food(self, lat: float, lon: float, radius_m: int = 60) -> list[dict]:
        q = (
            "[out:json][timeout:25];("
            f'nwr(around:{radius_m},{lat},{lon})["amenity"~"^({_AMENITY_RE})$"];'
            f'nwr(around:{radius_m},{lat},{lon})["shop"="bakery"];'
            ");out center 20;"
        )
        key = f"osm:nearby:{radius_m}:{round(lat, 6)}:{round(lon, 6)}"
        return self._fetch(
            key,
            lambda attempt: self._http.post(
                _OVERPASS_URLS[attempt % len(_OVERPASS_URLS)], data={"data": q}
            ),
            _parse_overpass,
        )

    def _pace(self) -> None:
        wait = self._min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _fetch(self, key: str, send, parse) -> list[dict]:
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:  # note: [] is a real hit, not a miss
                self.hits += 1
                return cached
        for attempt in range(_MAX_RETRIES + 1):
            self._pace()
            # An overloaded Overpass shows up two ways: a 5xx status, or a
            # request that hangs past the read timeout. Both retry against
            # the next mirror; both end in the same resume-later error.
            try:
                r = send(attempt)
            except httpx.TransportError as e:
                if attempt < _MAX_RETRIES:
                    time.sleep(min(2.0**attempt, 30.0))
                    continue
                raise _overloaded(f"kept timing out ({type(e).__name__})") from e
            if (r.status_code == 429 or r.status_code >= 500) and attempt < _MAX_RETRIES:
                time.sleep(_retry_delay(r, attempt))
                continue
            if r.status_code in (403, 429) or r.status_code >= 500:
                raise _overloaded(f"kept failing (HTTP {r.status_code})")
            r.raise_for_status()
            self.calls += 1
            places = parse(r.json())
            if self._cache is not None:
                self._cache.put(key, places)
            return places
        raise RuntimeError("unreachable")  # pragma: no cover


def _overloaded(what: str) -> PlacesError:
    # A dead run with a traceback would throw away nothing (the cache holds
    # every finished lookup), but say so instead of crashing.
    return PlacesError(
        f"OpenStreetMap {what} after {_MAX_RETRIES + 1} tries across its "
        "mirrors. The servers are rate-limiting or overloaded. Finished "
        "lookups are cached, so rerun in a few minutes and it resumes where "
        "it stopped."
    )


def _parse_nominatim(data: list) -> list[dict]:
    """Map Nominatim jsonv2 rows to the internal legacy-shaped dict."""
    out = []
    for item in data:
        display = item.get("display_name", "")
        head, _, rest = display.partition(",")
        mapped = _TYPE_MAP.get(item.get("type", ""))
        out.append(
            {
                "place_id": f"osm:{item.get('osm_type', 'node')}/{item.get('osm_id', '')}",
                "name": item.get("name") or head.strip(),
                "formatted_address": rest.strip() or display,
                "vicinity": rest.strip() or display,
                "types": [mapped or item.get("type") or "unknown"],
                "geometry": {
                    "location": {
                        "lat": float(item.get("lat", 0.0)),
                        "lng": float(item.get("lon", 0.0)),
                    }
                },
            }
        )
    return out


def _parse_overpass(data: dict) -> list[dict]:
    """Map Overpass elements to the internal legacy-shaped dict.

    Nodes carry lat/lon directly; ways and relations carry a center (the
    query says "out center"). Unnamed POIs are dropped: they can never become
    a Beli row she'd recognize.
    """
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        center = el.get("center") or {}
        raw = tags.get("amenity") or ("bakery" if tags.get("shop") == "bakery" else "")
        addr = " ".join(
            p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p
        )
        out.append(
            {
                "place_id": f"osm:{el.get('type', 'node')}/{el.get('id', '')}",
                "name": name,
                "formatted_address": addr,
                "vicinity": addr,
                "types": [_TYPE_MAP.get(raw, raw or "unknown")],
                "geometry": {
                    "location": {
                        "lat": el.get("lat", center.get("lat")),
                        "lng": el.get("lon", center.get("lon")),
                    }
                },
            }
        )
    return out

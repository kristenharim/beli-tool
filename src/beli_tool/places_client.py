from __future__ import annotations

import json
import time

import httpx

_BASE = "https://places.googleapis.com/v1"
_TEXT_FIELDS = "places.id,places.displayName,places.formattedAddress,places.types"
_NEARBY_FIELDS = (
    "places.id,places.displayName,places.formattedAddress,places.types,places.location"
)
_MAX_RETRIES = 5
_MAX_BACKOFF_S = 30.0


class PlacesError(RuntimeError):
    """A Places failure with a human-actionable message.

    The common setup mistakes (key typo'd, billing not enabled, Places API (New)
    not switched on, quota blown) all come back as bare HTTP codes. Raised as a
    plain traceback they read as a crash; the callers show this message instead.
    """


class PlacesClient:
    """Adapter over Google Places API (New).

    Calls the v1 endpoints and normalizes each place into the internal dict
    shape the matcher consumes: ``place_id``, ``name``, ``formatted_address``,
    ``vicinity``, ``types``, and ``geometry.location.lat/lng``. Keeping that
    contract here means ``matcher.py`` is unaware of the underlying API.

    Transient failures (HTTP 429 rate-limit and 5xx) are retried with
    exponential backoff, honoring a ``Retry-After`` header when present, so a
    single rate-limit blip during a large run doesn't abort the whole pipeline.

    An optional ``cache`` (see places_cache.PlacesCache) short-circuits repeat
    requests. It sits at ``_post``, the one chokepoint both endpoints route
    through, so the key is the exact request and both are covered at once.
    ``hits``/``calls`` count cache hits vs. billed network calls.
    """

    def __init__(self, api_key: str, client: httpx.Client | None = None, cache=None):
        self._key = api_key
        self._http = client or httpx.Client(timeout=15.0)
        self._cache = cache
        self.hits = 0
        self.calls = 0

    def _headers(self, field_mask: str) -> dict:
        return {
            "X-Goog-Api-Key": self._key,
            "X-Goog-FieldMask": field_mask,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, field_mask: str, body: dict) -> list[dict]:
        key = f"{path}:{json.dumps(body, sort_keys=True)}"
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:  # note: [] is a real hit, not a miss
                self.hits += 1
                return cached
        url = f"{_BASE}/{path}"
        for attempt in range(_MAX_RETRIES + 1):
            r = self._http.post(url, headers=self._headers(field_mask), json=body)
            if (r.status_code == 429 or r.status_code >= 500) and attempt < _MAX_RETRIES:
                time.sleep(_retry_delay(r, attempt))
                continue
            _raise_if_actionable(r)
            r.raise_for_status()
            self.calls += 1
            places = [_normalize(p) for p in r.json().get("places", [])]
            if self._cache is not None:
                self._cache.put(key, places)
            return places
        raise RuntimeError("unreachable")  # pragma: no cover

    def text_search(self, query: str) -> list[dict]:
        return self._post("places:searchText", _TEXT_FIELDS, {"textQuery": query})

    def nearby_food(self, lat: float, lon: float, radius_m: int = 60) -> list[dict]:
        return self._post(
            "places:searchNearby",
            _NEARBY_FIELDS,
            {
                "includedTypes": ["restaurant"],
                "maxResultCount": 20,
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lon},
                        "radius": float(radius_m),
                    }
                },
            },
        )


def _google_message(response: httpx.Response) -> str:
    try:
        return (response.json().get("error") or {}).get("message", "")
    except ValueError:
        return ""


def _raise_if_actionable(response: httpx.Response) -> None:
    """Turn the setup-mistake status codes into instructions, not tracebacks."""
    if response.status_code not in (400, 401, 403, 429):
        return
    detail = _google_message(response)
    tail = f"\n\nGoogle said: {detail}" if detail else ""
    if response.status_code == 429:
        raise PlacesError(
            "Google Places is rate-limiting or you're out of quota. Check the "
            "quota page for your project, or try again later." + tail
        )
    raise PlacesError(
        f"Google rejected the Places request (HTTP {response.status_code}). Usually one of:\n"
        "  • the API key in config.toml is wrong or restricted\n"
        "  • billing isn't enabled on the Google Cloud project\n"
        "  • the 'Places API (New)' isn't enabled for that project" + tail
    )


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Backoff before a retry: honor Retry-After, else exponential (capped)."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), _MAX_BACKOFF_S)
        except ValueError:
            pass
    return min(2.0**attempt, _MAX_BACKOFF_S)


def _normalize(p: dict) -> dict:
    """Map a Places API (New) place object to the internal legacy-shaped dict."""
    loc = p.get("location") or {}
    address = p.get("formattedAddress", "")
    return {
        "place_id": p.get("id", ""),
        "name": (p.get("displayName") or {}).get("text", ""),
        "formatted_address": address,
        "vicinity": address,
        "types": p.get("types", []),
        "geometry": {
            "location": {"lat": loc.get("latitude"), "lng": loc.get("longitude")}
        },
    }

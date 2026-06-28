from __future__ import annotations

import time

import httpx

_BASE = "https://places.googleapis.com/v1"
_TEXT_FIELDS = "places.id,places.displayName,places.formattedAddress,places.types"
_NEARBY_FIELDS = (
    "places.id,places.displayName,places.formattedAddress,places.types,places.location"
)
_MAX_RETRIES = 5
_MAX_BACKOFF_S = 30.0


class PlacesClient:
    """Adapter over Google Places API (New).

    Calls the v1 endpoints and normalizes each place into the internal dict
    shape the matcher consumes: ``place_id``, ``name``, ``formatted_address``,
    ``vicinity``, ``types``, and ``geometry.location.lat/lng``. Keeping that
    contract here means ``matcher.py`` is unaware of the underlying API.

    Transient failures (HTTP 429 rate-limit and 5xx) are retried with
    exponential backoff, honoring a ``Retry-After`` header when present, so a
    single rate-limit blip during a large run doesn't abort the whole pipeline.
    """

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self._key = api_key
        self._http = client or httpx.Client(timeout=15.0)

    def _headers(self, field_mask: str) -> dict:
        return {
            "X-Goog-Api-Key": self._key,
            "X-Goog-FieldMask": field_mask,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, field_mask: str, body: dict) -> list[dict]:
        url = f"{_BASE}/{path}"
        for attempt in range(_MAX_RETRIES + 1):
            r = self._http.post(url, headers=self._headers(field_mask), json=body)
            if (r.status_code == 429 or r.status_code >= 500) and attempt < _MAX_RETRIES:
                time.sleep(_retry_delay(r, attempt))
                continue
            r.raise_for_status()
            return [_normalize(p) for p in r.json().get("places", [])]
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

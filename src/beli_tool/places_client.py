from __future__ import annotations

import httpx

_BASE = "https://places.googleapis.com/v1"
_TEXT_FIELDS = "places.id,places.displayName,places.formattedAddress,places.types"
_NEARBY_FIELDS = (
    "places.id,places.displayName,places.formattedAddress,places.types,places.location"
)


class PlacesClient:
    """Adapter over Google Places API (New).

    Calls the v1 endpoints and normalizes each place into the internal dict
    shape the matcher consumes: ``place_id``, ``name``, ``formatted_address``,
    ``vicinity``, ``types``, and ``geometry.location.lat/lng``. Keeping that
    contract here means ``matcher.py`` is unaware of the underlying API.
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

    def text_search(self, query: str) -> list[dict]:
        r = self._http.post(
            f"{_BASE}/places:searchText",
            headers=self._headers(_TEXT_FIELDS),
            json={"textQuery": query},
        )
        r.raise_for_status()
        return [_normalize(p) for p in r.json().get("places", [])]

    def nearby_food(self, lat: float, lon: float, radius_m: int = 60) -> list[dict]:
        r = self._http.post(
            f"{_BASE}/places:searchNearby",
            headers=self._headers(_NEARBY_FIELDS),
            json={
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
        r.raise_for_status()
        return [_normalize(p) for p in r.json().get("places", [])]


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

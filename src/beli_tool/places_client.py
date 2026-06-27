from __future__ import annotations

import httpx

_BASE = "https://maps.googleapis.com/maps/api/place"


class PlacesClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self._key = api_key
        self._http = client or httpx.Client(timeout=15.0)

    def text_search(self, query: str) -> list[dict]:
        r = self._http.get(
            f"{_BASE}/textsearch/json",
            params={"query": query, "key": self._key},
        )
        r.raise_for_status()
        return r.json().get("results", [])

    def nearby_food(self, lat: float, lon: float, radius_m: int = 60) -> list[dict]:
        r = self._http.get(
            f"{_BASE}/nearbysearch/json",
            params={
                "location": f"{lat},{lon}",
                "radius": radius_m,
                "type": "restaurant",
                "key": self._key,
            },
        )
        r.raise_for_status()
        return r.json().get("results", [])

# Beli Staging Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Mac tool that aggregates Google Maps saved lists and GPS-stamped photos, matches them to restaurants, dedupes against a local ledger, and serves a phone-friendly worklist for fast ranking + manual entry into Beli.

**Architecture:** A standalone Python **core package** (`beli_tool`) does extract → match → dedupe with no dependency on the web layer. A thin FastAPI **web app** is one front-end driving the core. A CLI wires real data sources together and launches the server. External effects (Apple Photos, Google Places) sit behind small adapters so the logic is unit-testable with stubs/mocks.

**Tech Stack:** Python 3.11+, `osxphotos` (Photos GPS), `httpx` (Google Places API), `fastapi` + `uvicorn` (web app), `pydantic` v2 (models), `sqlite3` (ledger), `pytest` (tests). Built with `setuptools`; run in a `venv`.

## Global Constraints

- Python **3.11+** (uses stdlib `tomllib`).
- Project lives at `~/beli-tool` — **never** under iCloud Drive (sync corrupts the venv/SQLite).
- The **core package must not import the web layer**; the web app imports the core, never the reverse.
- Photo → restaurant matching uses the **GPS coordinate embedded in photo metadata**, never image-content recognition.
- The ledger is keyed by Google Places **`place_id`**; dedupe means "skip any `place_id` already handled."
- The tool never writes into Beli; final entry is manual. No automation of Beli's app or private API.
- All external effects (Apple Photos read, Google Places HTTP) live behind adapter classes so logic is testable without them.

---

### Task 1: Project scaffold + data models

**Files:**
- Create: `pyproject.toml`
- Create: `src/beli_tool/__init__.py`
- Create: `src/beli_tool/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `RawPlace(source: Literal["maps","photos"], name: str|None=None, address: str|None=None, lat: float|None=None, lon: float|None=None, visit_date: date|None=None, photo_ref: str|None=None, photo_count: int=0, source_list: str|None=None)`
  - `PlaceCandidate(place_id: str, name: str, address: str, category: str, distance_m: float|None=None)`
  - `MatchedPlace(bucket: Literal["been","want_to_try"], status: Literal["confident","ambiguous","no_match"], raw: RawPlace, match: PlaceCandidate|None=None, candidates: list[PlaceCandidate]=[])`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "beli-tool"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "osxphotos>=0.68",
  "httpx>=0.27",
  "fastapi>=0.110",
  "uvicorn>=0.29",
  "pydantic>=2.6",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
beli-tool = "beli_tool.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Create the venv and install (editable, with dev deps)**

Run:
```bash
cd ~/beli-tool && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
```
Expected: ends with `Successfully installed beli-tool-0.1.0 ...` (and pytest, fastapi, etc.).

- [ ] **Step 3: Create `src/beli_tool/__init__.py`**

```python
__all__ = ["__version__"]
__version__ = "0.1.0"
```

- [ ] **Step 4: Write the failing test** in `tests/test_models.py`

```python
from datetime import date
from beli_tool.models import RawPlace, PlaceCandidate, MatchedPlace


def test_rawplace_defaults():
    rp = RawPlace(source="maps", name="Lilia", source_list="Want to go")
    assert rp.lat is None and rp.photo_count == 0


def test_matchedplace_holds_candidate():
    cand = PlaceCandidate(place_id="abc", name="Lilia", address="567 Union Ave", category="restaurant")
    mp = MatchedPlace(
        bucket="been",
        status="confident",
        raw=RawPlace(source="photos", lat=40.7, lon=-73.9, visit_date=date(2026, 4, 12)),
        match=cand,
    )
    assert mp.match.place_id == "abc"
    assert mp.candidates == []
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd ~/beli-tool && . .venv/bin/activate && pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.models'`.

- [ ] **Step 6: Write `src/beli_tool/models.py`**

```python
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class RawPlace(BaseModel):
    source: Literal["maps", "photos"]
    name: str | None = None
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    visit_date: date | None = None
    photo_ref: str | None = None
    photo_count: int = 0
    source_list: str | None = None


class PlaceCandidate(BaseModel):
    place_id: str
    name: str
    address: str
    category: str
    distance_m: float | None = None


class MatchedPlace(BaseModel):
    bucket: Literal["been", "want_to_try"]
    status: Literal["confident", "ambiguous", "no_match"]
    raw: RawPlace
    match: PlaceCandidate | None = None
    candidates: list[PlaceCandidate] = Field(default_factory=list)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 8: Commit**

```bash
cd ~/beli-tool && git add pyproject.toml src/beli_tool/__init__.py src/beli_tool/models.py tests/test_models.py
git commit -m "feat: project scaffold and core data models"
```

---

### Task 2: Config loader

**Files:**
- Create: `src/beli_tool/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Config(api_key: str, saved_dir: Path, db_path: Path)` and `load_config(path: str|Path|None=None) -> Config`. Reads TOML; falls back to env var `BELI_PLACES_KEY`; raises `RuntimeError` if no key.

- [ ] **Step 1: Write the failing test** in `tests/test_config.py`

```python
import pytest
from beli_tool.config import load_config


def test_load_config_reads_toml(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('google_places_api_key = "KEY123"\n')
    cfg = load_config(cfg_file)
    assert cfg.api_key == "KEY123"
    assert cfg.saved_dir.name == "inbox"


def test_load_config_missing_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("BELI_PLACES_KEY", raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("saved_dir = \"/tmp/x\"\n")
    with pytest.raises(RuntimeError):
        load_config(cfg_file)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.config'`.

- [ ] **Step 3: Write `src/beli_tool/config.py`**

```python
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOME = Path.home() / "beli-tool"


@dataclass
class Config:
    api_key: str
    saved_dir: Path
    db_path: Path


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path else DEFAULT_HOME / "config.toml"
    data: dict = {}
    if path.exists():
        data = tomllib.loads(path.read_text())
    api_key = data.get("google_places_api_key") or os.environ.get("BELI_PLACES_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Missing Google Places API key. Set google_places_api_key in "
            "config.toml or the BELI_PLACES_KEY environment variable."
        )
    saved_dir = Path(data.get("saved_dir", DEFAULT_HOME / "inbox"))
    db_path = Path(data.get("db_path", DEFAULT_HOME / "ledger.sqlite"))
    return Config(api_key=api_key, saved_dir=saved_dir, db_path=db_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/beli-tool && git add src/beli_tool/config.py tests/test_config.py
git commit -m "feat: config loader with TOML + env fallback"
```

---

### Task 3: Maps collector (Takeout CSV → RawPlace)

**Files:**
- Create: `src/beli_tool/maps_collector.py`
- Test: `tests/test_maps_collector.py`
- Test fixture: `tests/fixtures/Want to go.csv`

**Interfaces:**
- Consumes: `RawPlace` (Task 1).
- Produces: `collect_maps(saved_dir: Path) -> list[RawPlace]`. Reads every `*.csv` in `saved_dir`; each row's `Title` column becomes a `RawPlace(source="maps", name=Title, source_list=<csv filename stem>)`. Skips rows with empty Title.

- [ ] **Step 1: Create the fixture** `tests/fixtures/Want to go.csv`

```csv
Title,Note,URL
Tatiana by Kwame Onwuachi,,https://maps.google.com/?cid=1
Dhamaka,,https://maps.google.com/?cid=2
,,https://maps.google.com/?cid=3
```

- [ ] **Step 2: Write the failing test** in `tests/test_maps_collector.py`

```python
from pathlib import Path
from beli_tool.maps_collector import collect_maps

FIXTURES = Path(__file__).parent / "fixtures"


def test_collect_maps_reads_titles_and_skips_blank():
    places = collect_maps(FIXTURES)
    names = [p.name for p in places]
    assert "Tatiana by Kwame Onwuachi" in names
    assert "Dhamaka" in names
    assert len(places) == 2  # blank-title row skipped
    assert all(p.source == "maps" for p in places)
    assert places[0].source_list == "Want to go"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_maps_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.maps_collector'`.

- [ ] **Step 4: Write `src/beli_tool/maps_collector.py`**

```python
from __future__ import annotations

import csv
from pathlib import Path

from beli_tool.models import RawPlace


def collect_maps(saved_dir: str | Path) -> list[RawPlace]:
    saved_dir = Path(saved_dir)
    places: list[RawPlace] = []
    for csv_path in sorted(saved_dir.glob("*.csv")):
        list_name = csv_path.stem
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                title = (row.get("Title") or "").strip()
                if not title:
                    continue
                places.append(
                    RawPlace(source="maps", name=title, source_list=list_name)
                )
    return places
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_maps_collector.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
cd ~/beli-tool && git add src/beli_tool/maps_collector.py tests/test_maps_collector.py "tests/fixtures/Want to go.csv"
git commit -m "feat: maps collector parses Takeout saved-list CSVs"
```

---

### Task 4: Geo-time photo clustering (pure logic)

**Files:**
- Create: `src/beli_tool/clustering.py`
- Test: `tests/test_clustering.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `haversine_m(lat1, lon1, lat2, lon2) -> float`
  - `PhotoPoint(id: str, lat: float, lon: float, taken: datetime)` (dataclass)
  - `Cluster` (dataclass) with `.points: list[PhotoPoint]` and properties `.lat`, `.lon`, `.count`, `.earliest`
  - `cluster_photos(points: list[PhotoPoint], radius_m: float=75.0, time_gap_hours: float=6.0) -> list[Cluster]`. Greedy: a point joins an existing cluster if within `radius_m` of its centroid AND within `time_gap_hours` of that cluster's most recent point; else it starts a new cluster. Input is processed in time order.

- [ ] **Step 1: Write the failing test** in `tests/test_clustering.py`

```python
from datetime import datetime
from beli_tool.clustering import PhotoPoint, cluster_photos, haversine_m


def test_haversine_known_distance():
    # ~111.2 m per 0.001 deg latitude near the equator-ish; assert order of magnitude
    d = haversine_m(40.7180, -73.9568, 40.7184, -73.9568)
    assert 30 < d < 60


def test_two_visits_split_by_distance():
    pts = [
        PhotoPoint("a", 40.7184, -73.9568, datetime(2026, 4, 12, 19, 0)),
        PhotoPoint("b", 40.7184, -73.9569, datetime(2026, 4, 12, 19, 10)),
        PhotoPoint("c", 40.7220, -73.9876, datetime(2026, 4, 12, 19, 5)),
    ]
    clusters = cluster_photos(pts)
    assert len(clusters) == 2
    counts = sorted(c.count for c in clusters)
    assert counts == [1, 2]


def test_same_place_different_day_splits_by_time():
    pts = [
        PhotoPoint("a", 40.7184, -73.9568, datetime(2026, 4, 12, 19, 0)),
        PhotoPoint("b", 40.7184, -73.9568, datetime(2026, 4, 20, 19, 0)),
    ]
    assert len(cluster_photos(pts)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clustering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.clustering'`.

- [ ] **Step 3: Write `src/beli_tool/clustering.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clustering.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/beli-tool && git add src/beli_tool/clustering.py tests/test_clustering.py
git commit -m "feat: geo-time photo clustering"
```

---

### Task 5: Photos source adapter + photos collector

**Files:**
- Create: `src/beli_tool/photos_source.py`
- Create: `src/beli_tool/photos_collector.py`
- Test: `tests/test_photos_collector.py`

**Interfaces:**
- Consumes: `PhotoPoint`, `cluster_photos`, `Cluster` (Task 4); `RawPlace` (Task 1).
- Produces:
  - Protocol `PhotoSource` with `points(self) -> list[PhotoPoint]`.
  - `OsxPhotosSource` implementing `PhotoSource` via `osxphotos` (skips photos with no GPS or no date).
  - `collect_photos(source: PhotoSource, radius_m: float=75.0, time_gap_hours: float=6.0) -> list[RawPlace]`. Each cluster → `RawPlace(source="photos", lat=centroid_lat, lon=centroid_lon, visit_date=earliest.date(), photo_count=count, photo_ref=first_point_id)`.

- [ ] **Step 1: Write the failing test** in `tests/test_photos_collector.py` (uses a stub source — no real Photos library)

```python
from datetime import datetime
from beli_tool.clustering import PhotoPoint
from beli_tool.photos_collector import collect_photos


class StubSource:
    def __init__(self, pts):
        self._pts = pts

    def points(self):
        return self._pts


def test_collect_photos_makes_one_rawplace_per_cluster():
    src = StubSource([
        PhotoPoint("a", 40.7184, -73.9568, datetime(2026, 4, 12, 19, 0)),
        PhotoPoint("b", 40.7184, -73.9569, datetime(2026, 4, 12, 19, 10)),
        PhotoPoint("c", 40.7220, -73.9876, datetime(2026, 3, 3, 13, 0)),
    ])
    raws = collect_photos(src)
    assert len(raws) == 2
    assert all(r.source == "photos" for r in raws)
    dinner = [r for r in raws if r.photo_count == 2][0]
    assert dinner.visit_date.isoformat() == "2026-04-12"
    assert dinner.photo_ref in {"a", "b"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_photos_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.photos_collector'`.

- [ ] **Step 3: Write `src/beli_tool/photos_source.py`**

```python
from __future__ import annotations

from typing import Protocol

from beli_tool.clustering import PhotoPoint


class PhotoSource(Protocol):
    def points(self) -> list[PhotoPoint]: ...


class OsxPhotosSource:
    """Reads the local Apple Photos library; keeps only GPS-stamped, dated photos."""

    def points(self) -> list[PhotoPoint]:
        import osxphotos

        db = osxphotos.PhotosDB()
        out: list[PhotoPoint] = []
        for p in db.photos():
            loc = p.location  # (lat, lon) or (None, None)
            if loc and loc[0] is not None and loc[1] is not None and p.date:
                out.append(PhotoPoint(id=p.uuid, lat=loc[0], lon=loc[1], taken=p.date))
        return out
```

- [ ] **Step 4: Write `src/beli_tool/photos_collector.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_photos_collector.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
cd ~/beli-tool && git add src/beli_tool/photos_source.py src/beli_tool/photos_collector.py tests/test_photos_collector.py
git commit -m "feat: photos source adapter and collector"
```

---

### Task 6: Places client adapter + matcher

**Files:**
- Create: `src/beli_tool/places_client.py`
- Create: `src/beli_tool/matcher.py`
- Test: `tests/test_matcher.py`

**Interfaces:**
- Consumes: `RawPlace`, `PlaceCandidate`, `MatchedPlace` (Task 1); `haversine_m` (Task 4).
- Produces:
  - `PlacesClient(api_key: str)` with `text_search(query: str) -> list[dict]` (Places Text Search) and `nearby_food(lat: float, lon: float, radius_m: int=60) -> list[dict]` (Places Nearby Search, `type=restaurant`). Each returns Google's raw `results` list.
  - `match_maps_place(raw: RawPlace, client) -> MatchedPlace` — text-search the name; confident on first result, else `no_match`. Bucket `want_to_try`.
  - `match_photo_cluster(raw: RawPlace, client, ambiguous_radius_m: float=25.0) -> MatchedPlace` — nearby food POIs; `no_match` if none; `ambiguous` (with `candidates`) if ≥2 within `ambiguous_radius_m`; else `confident` with nearest. Bucket `been`.

- [ ] **Step 1: Write the failing test** in `tests/test_matcher.py` (mock client — no network)

```python
from datetime import date
from beli_tool.models import RawPlace
from beli_tool.matcher import match_maps_place, match_photo_cluster


class FakeClient:
    def __init__(self, text=None, nearby=None):
        self._text = text or []
        self._nearby = nearby or []

    def text_search(self, query):
        return self._text

    def nearby_food(self, lat, lon, radius_m=60):
        return self._nearby


def test_match_maps_confident():
    client = FakeClient(text=[
        {"place_id": "p1", "name": "Dhamaka", "formatted_address": "119 Delancey St",
         "types": ["restaurant", "food"]},
    ])
    m = match_maps_place(RawPlace(source="maps", name="Dhamaka"), client)
    assert m.status == "confident" and m.bucket == "want_to_try"
    assert m.match.place_id == "p1"


def test_match_maps_no_results():
    m = match_maps_place(RawPlace(source="maps", name="Nowhere"), FakeClient(text=[]))
    assert m.status == "no_match" and m.match is None


def test_match_photo_confident_single():
    nearby = [
        {"place_id": "p1", "name": "Lilia", "vicinity": "567 Union Ave",
         "types": ["restaurant"], "geometry": {"location": {"lat": 40.7184, "lng": -73.9568}}},
    ]
    raw = RawPlace(source="photos", lat=40.7184, lon=-73.9568, visit_date=date(2026, 4, 12))
    m = match_photo_cluster(raw, FakeClient(nearby=nearby))
    assert m.status == "confident" and m.bucket == "been"
    assert m.match.name == "Lilia"


def test_match_photo_ambiguous_two_close():
    nearby = [
        {"place_id": "p1", "name": "Los Tacos No. 1", "vicinity": "75 9th Ave",
         "types": ["restaurant"], "geometry": {"location": {"lat": 40.7220, "lng": -73.9876}}},
        {"place_id": "p2", "name": "Time Out Market", "vicinity": "55 Water St",
         "types": ["restaurant"], "geometry": {"location": {"lat": 40.72205, "lng": -73.98762}}},
    ]
    raw = RawPlace(source="photos", lat=40.7220, lon=-73.9876)
    m = match_photo_cluster(raw, FakeClient(nearby=nearby))
    assert m.status == "ambiguous"
    assert {c.place_id for c in m.candidates} == {"p1", "p2"}
    assert m.match is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.matcher'`.

- [ ] **Step 3: Write `src/beli_tool/places_client.py`**

```python
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
```

- [ ] **Step 4: Write `src/beli_tool/matcher.py`**

```python
from __future__ import annotations

from beli_tool.clustering import haversine_m
from beli_tool.models import MatchedPlace, PlaceCandidate, RawPlace

_FOOD_TYPES = {"restaurant", "food", "cafe", "bar", "bakery", "meal_takeaway"}


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
    cands.sort(key=lambda c: c.distance_m if c.distance_m is not None else 1e9)

    near = [c for c in cands if (c.distance_m or 1e9) <= ambiguous_radius_m]
    if len(near) >= 2:
        return MatchedPlace(bucket="been", status="ambiguous", raw=raw, candidates=near)
    return MatchedPlace(bucket="been", status="confident", raw=raw, match=cands[0])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_matcher.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
cd ~/beli-tool && git add src/beli_tool/places_client.py src/beli_tool/matcher.py tests/test_matcher.py
git commit -m "feat: Google Places client adapter and matcher"
```

---

### Task 7: Ledger (SQLite dedupe store)

**Files:**
- Create: `src/beli_tool/ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Ledger(db_path: str|Path)` (creates table if missing; `:memory:` allowed) with:
  - `handled_ids(self) -> set[str]`
  - `is_handled(self, place_id: str) -> bool`
  - `mark_added(self, place_id: str, name: str, bucket: str, rating: str|None=None) -> None`
  - `mark_dismissed(self, place_id: str, name: str="", bucket: str="") -> None`

- [ ] **Step 1: Write the failing test** in `tests/test_ledger.py`

```python
from beli_tool.ledger import Ledger


def test_ledger_marks_and_dedupes():
    led = Ledger(":memory:")
    assert led.handled_ids() == set()
    led.mark_added("p1", "Lilia", "been", rating="loved")
    assert led.is_handled("p1")
    assert "p1" in led.handled_ids()


def test_ledger_dismiss_counts_as_handled():
    led = Ledger(":memory:")
    led.mark_dismissed("p2", "Somewhere", "want_to_try")
    assert led.is_handled("p2")


def test_ledger_reinsert_is_idempotent():
    led = Ledger(":memory:")
    led.mark_added("p1", "Lilia", "been", "loved")
    led.mark_added("p1", "Lilia", "been", "fine")
    assert len(led.handled_ids()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.ledger'`.

- [ ] **Step 3: Write `src/beli_tool/ledger.py`**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path


class Ledger:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS handled (
                place_id TEXT PRIMARY KEY,
                name TEXT,
                bucket TEXT,
                rating TEXT,
                action TEXT,
                ts TEXT DEFAULT (datetime('now'))
            )"""
        )
        self.conn.commit()

    def handled_ids(self) -> set[str]:
        return {row[0] for row in self.conn.execute("SELECT place_id FROM handled")}

    def is_handled(self, place_id: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM handled WHERE place_id = ?", (place_id,)
        )
        return cur.fetchone() is not None

    def _upsert(self, place_id, name, bucket, rating, action) -> None:
        self.conn.execute(
            """INSERT INTO handled (place_id, name, bucket, rating, action)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(place_id) DO UPDATE SET
                 name=excluded.name, bucket=excluded.bucket,
                 rating=excluded.rating, action=excluded.action,
                 ts=datetime('now')""",
            (place_id, name, bucket, rating, action),
        )
        self.conn.commit()

    def mark_added(self, place_id, name, bucket, rating=None) -> None:
        self._upsert(place_id, name, bucket, rating, "added")

    def mark_dismissed(self, place_id, name="", bucket="") -> None:
        self._upsert(place_id, name, bucket, None, "dismissed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ledger.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/beli-tool && git add src/beli_tool/ledger.py tests/test_ledger.py
git commit -m "feat: SQLite ledger for dedupe"
```

---

### Task 8: Pipeline (build deduped queue)

**Files:**
- Create: `src/beli_tool/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `RawPlace`, `MatchedPlace` (Task 1); `match_maps_place`, `match_photo_cluster` (Task 6); `Ledger` (Task 7).
- Produces:
  - `Queue(want_to_try: list[MatchedPlace], been: list[MatchedPlace], review: list[MatchedPlace])` (dataclass).
  - `build_queue(maps_places: list[RawPlace], photo_raws: list[RawPlace], client, ledger: Ledger) -> Queue`. Maps: `confident` → `want_to_try` unless its `place_id` is handled; `no_match` → `review`. Photos: `confident` and `ambiguous` → `been` (ambiguous shown with picker), dropping confident matches whose `place_id` is handled; `no_match` → `review`.

- [ ] **Step 1: Write the failing test** in `tests/test_pipeline.py`

```python
from datetime import date
from beli_tool.models import RawPlace
from beli_tool.ledger import Ledger
from beli_tool.pipeline import build_queue


class FakeClient:
    def text_search(self, query):
        return [{"place_id": "w1", "name": query, "formatted_address": "x",
                 "types": ["restaurant"]}]

    def nearby_food(self, lat, lon, radius_m=60):
        return [{"place_id": "b1", "name": "Lilia", "vicinity": "567 Union Ave",
                 "types": ["restaurant"],
                 "geometry": {"location": {"lat": lat, "lng": lon}}}]


def test_build_queue_sorts_and_dedupes():
    maps = [RawPlace(source="maps", name="Dhamaka")]
    photos = [RawPlace(source="photos", lat=40.7, lon=-73.9, visit_date=date(2026, 4, 12))]
    led = Ledger(":memory:")
    q = build_queue(maps, photos, FakeClient(), led)
    assert [m.match.name for m in q.want_to_try] == ["Dhamaka"]
    assert [m.match.name for m in q.been] == ["Lilia"]

    # mark the photo place handled -> disappears next build
    led.mark_added("b1", "Lilia", "been", "loved")
    q2 = build_queue(maps, photos, FakeClient(), led)
    assert q2.been == []
    assert [m.match.name for m in q2.want_to_try] == ["Dhamaka"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.pipeline'`.

- [ ] **Step 3: Write `src/beli_tool/pipeline.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from beli_tool.ledger import Ledger
from beli_tool.matcher import match_maps_place, match_photo_cluster
from beli_tool.models import MatchedPlace, RawPlace


@dataclass
class Queue:
    want_to_try: list[MatchedPlace] = field(default_factory=list)
    been: list[MatchedPlace] = field(default_factory=list)
    review: list[MatchedPlace] = field(default_factory=list)


def build_queue(
    maps_places: list[RawPlace],
    photo_raws: list[RawPlace],
    client,
    ledger: Ledger,
) -> Queue:
    handled = ledger.handled_ids()
    q = Queue()

    for raw in maps_places:
        m = match_maps_place(raw, client)
        if m.status == "no_match":
            q.review.append(m)
        elif m.match and m.match.place_id in handled:
            continue
        else:
            q.want_to_try.append(m)

    for raw in photo_raws:
        m = match_photo_cluster(raw, client)
        if m.status == "no_match":
            q.review.append(m)
        elif m.status == "confident" and m.match and m.match.place_id in handled:
            continue
        else:
            q.been.append(m)

    return q
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/beli-tool && git add src/beli_tool/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline builds deduped queue"
```

---

### Task 9: Web app (FastAPI endpoints + page)

**Files:**
- Create: `src/beli_tool/webapp.py`
- Create: `src/beli_tool/templates/index.html`
- Test: `tests/test_webapp.py`

**Interfaces:**
- Consumes: `Queue` (Task 8); `Ledger` (Task 7); `MatchedPlace` (Task 1).
- Produces: `create_app(queue: Queue, ledger: Ledger) -> fastapi.FastAPI` with:
  - `GET /` → the HTML page.
  - `GET /api/queue` → `{"want_to_try": [...], "been": [...], "review": [...]}` excluding any item whose chosen `place_id` is already handled; each item serialized as `{place_id, name, address, bucket, status, visit_date, photo_count, candidates: [{place_id, name, address}]}` (for confident items `place_id`/`name`/`address` come from `match`; for ambiguous, `place_id` is `null` and `candidates` is populated).
  - `POST /api/added` body `{place_id, name, bucket, rating?}` → `ledger.mark_added(...)` → `{"ok": true}`.
  - `POST /api/skip` body `{place_id, name?, bucket?}` → `ledger.mark_dismissed(...)` → `{"ok": true}`.

- [ ] **Step 1: Write the failing test** in `tests/test_webapp.py`

```python
from datetime import date
from fastapi.testclient import TestClient

from beli_tool.models import MatchedPlace, PlaceCandidate, RawPlace
from beli_tool.pipeline import Queue
from beli_tool.ledger import Ledger
from beli_tool.webapp import create_app


def _queue():
    been = MatchedPlace(
        bucket="been", status="confident",
        raw=RawPlace(source="photos", lat=40.7, lon=-73.9, visit_date=date(2026, 4, 12), photo_count=4),
        match=PlaceCandidate(place_id="b1", name="Lilia", address="567 Union Ave", category="restaurant"),
    )
    want = MatchedPlace(
        bucket="want_to_try", status="confident",
        raw=RawPlace(source="maps", name="Dhamaka"),
        match=PlaceCandidate(place_id="w1", name="Dhamaka", address="119 Delancey", category="restaurant"),
    )
    return Queue(want_to_try=[want], been=[been])


def test_queue_endpoint_lists_items():
    client = TestClient(create_app(_queue(), Ledger(":memory:")))
    data = client.get("/api/queue").json()
    assert [i["name"] for i in data["been"]] == ["Lilia"]
    assert data["been"][0]["photo_count"] == 4
    assert [i["name"] for i in data["want_to_try"]] == ["Dhamaka"]


def test_added_marks_handled_and_filters_next_queue():
    led = Ledger(":memory:")
    client = TestClient(create_app(_queue(), led))
    r = client.post("/api/added", json={"place_id": "b1", "name": "Lilia", "bucket": "been", "rating": "loved"})
    assert r.json() == {"ok": True}
    assert led.is_handled("b1")
    data = client.get("/api/queue").json()
    assert data["been"] == []  # filtered out after being handled


def test_index_serves_html():
    client = TestClient(create_app(_queue(), Ledger(":memory:")))
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_webapp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.webapp'`.

- [ ] **Step 3: Write `src/beli_tool/templates/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Beli staging</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 16px; }
  h2 { font-weight: 500; }
  .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin: 12px 0; }
  .muted { color: #777; font-size: 14px; }
  button { font-size: 16px; padding: 10px 14px; margin: 4px 4px 0 0; border-radius: 8px; border: 1px solid #ccc; background: #fff; }
  .added { background: #e6f1fb; }
</style>
</head>
<body>
<h2>Want to try (<span id="want-count">0</span>)</h2>
<div id="want"></div>
<h2>Been (<span id="been-count">0</span>)</h2>
<div id="been"></div>
<script>
async function load() {
  const q = await (await fetch('/api/queue')).json();
  render('want', q.want_to_try, false);
  render('been', q.been, true);
  document.getElementById('want-count').textContent = q.want_to_try.length;
  document.getElementById('been-count').textContent = q.been.length;
}
function render(id, items, isBeen) {
  const root = document.getElementById(id);
  root.innerHTML = '';
  for (const it of items) {
    const div = document.createElement('div');
    div.className = 'card';
    let inner = `<div><strong>${it.name ?? '(pick one below)'}</strong></div>`
      + `<div class="muted">${it.address ?? ''}</div>`;
    if (isBeen && it.visit_date) inner += `<div class="muted">${it.visit_date} · ${it.photo_count} photos</div>`;
    if (it.status === 'ambiguous') {
      inner += '<div class="muted">Which place?</div>';
      for (const c of it.candidates) {
        inner += `<button onclick="added('${c.place_id}','${c.name.replace(/'/g,"")}','${it.bucket}', null)">${c.name}</button>`;
      }
    } else {
      if (isBeen) {
        for (const [emoji, val] of [['😍','loved'],['😐','fine'],['😞','disliked']]) {
          inner += `<button data-rating="${val}">${emoji}</button>`;
        }
      }
      inner += `<button onclick="copyOpen('${(it.name||'').replace(/'/g,"")}')">Copy & open Beli</button>`;
      inner += `<button class="added" onclick="added('${it.place_id}','${(it.name||'').replace(/'/g,"")}','${it.bucket}', currentRating(this))">Added ✓</button>`;
      inner += `<button onclick="skip('${it.place_id}')">Skip</button>`;
    }
    div.innerHTML = inner;
    root.appendChild(div);
  }
}
function currentRating(btn){ const r = btn.parentElement.querySelector('[data-rating].sel'); return r ? r.dataset.rating : null; }
document.addEventListener('click', e => { if (e.target.dataset && e.target.dataset.rating) {
  e.target.parentElement.querySelectorAll('[data-rating]').forEach(b=>b.classList.remove('sel'));
  e.target.classList.add('sel'); } });
function copyOpen(name){ navigator.clipboard && navigator.clipboard.writeText(name); window.location.href = 'beli://'; }
async function added(place_id, name, bucket, rating){
  await fetch('/api/added', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({place_id, name, bucket, rating})}); load();
}
async function skip(place_id){
  await fetch('/api/skip', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({place_id})}); load();
}
load();
</script>
</body>
</html>
```

- [ ] **Step 4: Write `src/beli_tool/webapp.py`**

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from beli_tool.ledger import Ledger
from beli_tool.models import MatchedPlace
from beli_tool.pipeline import Queue

_INDEX = (Path(__file__).parent / "templates" / "index.html").read_text()


class AddedReq(BaseModel):
    place_id: str
    name: str
    bucket: str
    rating: str | None = None


class SkipReq(BaseModel):
    place_id: str
    name: str = ""
    bucket: str = ""


def _serialize(m: MatchedPlace) -> dict:
    vd = m.raw.visit_date.isoformat() if m.raw.visit_date else None
    return {
        "place_id": m.match.place_id if m.match else None,
        "name": m.match.name if m.match else None,
        "address": m.match.address if m.match else None,
        "bucket": m.bucket,
        "status": m.status,
        "visit_date": vd,
        "photo_count": m.raw.photo_count,
        "candidates": [
            {"place_id": c.place_id, "name": c.name, "address": c.address}
            for c in m.candidates
        ],
    }


def _visible(items: list[MatchedPlace], handled: set[str]) -> list[dict]:
    out = []
    for m in items:
        if m.match and m.match.place_id in handled:
            continue
        out.append(_serialize(m))
    return out


def create_app(queue: Queue, ledger: Ledger) -> FastAPI:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX

    @app.get("/api/queue")
    def get_queue() -> dict:
        handled = ledger.handled_ids()
        return {
            "want_to_try": _visible(queue.want_to_try, handled),
            "been": _visible(queue.been, handled),
            "review": _visible(queue.review, handled),
        }

    @app.post("/api/added")
    def added(req: AddedReq) -> dict:
        ledger.mark_added(req.place_id, req.name, req.bucket, req.rating)
        return {"ok": True}

    @app.post("/api/skip")
    def skip(req: SkipReq) -> dict:
        ledger.mark_dismissed(req.place_id, req.name, req.bucket)
        return {"ok": True}

    return app
```

- [ ] **Step 5: Ensure the template ships in the package** — add to `pyproject.toml` under `[tool.setuptools]`

```toml
[tool.setuptools]
include-package-data = true

[tool.setuptools.package-data]
beli_tool = ["templates/*.html"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_webapp.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
cd ~/beli-tool && git add src/beli_tool/webapp.py src/beli_tool/templates/index.html tests/test_webapp.py pyproject.toml
git commit -m "feat: FastAPI web app serving the staging worklist"
```

---

### Task 10: CLI entry point (`beli-tool run`)

**Files:**
- Create: `src/beli_tool/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config` (Task 2), `collect_maps` (Task 3), `collect_photos` + `OsxPhotosSource` (Task 5), `PlacesClient` (Task 6), `Ledger` (Task 7), `build_queue` (Task 8), `create_app` (Task 9).
- Produces:
  - `local_ip() -> str` — best-effort LAN IP for the printed URL (falls back to `127.0.0.1`).
  - `build_app_from_config(cfg, photo_source=None, client=None) -> tuple[FastAPI, Ledger]` — wires real sources (override-able for tests).
  - `main(argv: list[str]|None=None) -> None` — `beli-tool run` builds the app and launches uvicorn on `0.0.0.0:8000`, printing the phone URL.

- [ ] **Step 1: Write the failing test** in `tests/test_cli.py` (tests wiring, not the server loop)

```python
from datetime import date
from beli_tool.config import Config
from beli_tool.cli import build_app_from_config, local_ip


class FakeSource:
    def points(self):
        return []


class FakeClient:
    def text_search(self, query):
        return [{"place_id": "w1", "name": query, "formatted_address": "x", "types": ["restaurant"]}]

    def nearby_food(self, lat, lon, radius_m=60):
        return []


def test_local_ip_returns_string():
    assert isinstance(local_ip(), str)


def test_build_app_from_config_wires_sources(tmp_path):
    (tmp_path / "Want to go.csv").write_text("Title,Note,URL\nDhamaka,,u\n")
    cfg = Config(api_key="k", saved_dir=tmp_path, db_path=tmp_path / "l.sqlite")
    app, ledger = build_app_from_config(cfg, photo_source=FakeSource(), client=FakeClient())
    from fastapi.testclient import TestClient
    data = TestClient(app).get("/api/queue").json()
    assert [i["name"] for i in data["want_to_try"]] == ["Dhamaka"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beli_tool.cli'`.

- [ ] **Step 3: Write `src/beli_tool/cli.py`**

```python
from __future__ import annotations

import socket
import sys

import uvicorn
from fastapi import FastAPI

from beli_tool.config import Config, load_config
from beli_tool.ledger import Ledger
from beli_tool.maps_collector import collect_maps
from beli_tool.photos_collector import collect_photos
from beli_tool.photos_source import OsxPhotosSource
from beli_tool.pipeline import build_queue
from beli_tool.places_client import PlacesClient
from beli_tool.webapp import create_app


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def build_app_from_config(cfg: Config, photo_source=None, client=None) -> tuple[FastAPI, Ledger]:
    photo_source = photo_source or OsxPhotosSource()
    client = client or PlacesClient(cfg.api_key)
    ledger = Ledger(cfg.db_path)
    maps_places = collect_maps(cfg.saved_dir)
    photo_raws = collect_photos(photo_source)
    queue = build_queue(maps_places, photo_raws, client, ledger)
    return create_app(queue, ledger), ledger


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "run":
        print("usage: beli-tool run")
        return
    cfg = load_config()
    app, _ = build_app_from_config(cfg)
    port = 8000
    print(f"\n  Beli staging ready → open  http://{local_ip()}:{port}  on your phone\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: PASS (all tasks' tests green).

- [ ] **Step 6: Commit**

```bash
cd ~/beli-tool && git add src/beli_tool/cli.py tests/test_cli.py
git commit -m "feat: CLI entry point wiring sources and launching the web app"
```

---

### Task 11: README + config template (usable end-to-end)

**Files:**
- Create: `README.md`
- Create: `config.example.toml`

**Interfaces:**
- Consumes: everything above (documentation only).
- Produces: setup + run docs. No tests (docs task).

- [ ] **Step 1: Create `config.example.toml`**

```toml
google_places_api_key = "PASTE_YOUR_KEY_HERE"
saved_dir = "~/beli-tool/inbox"
db_path = "~/beli-tool/ledger.sqlite"
```

- [ ] **Step 2: Create `README.md`**

````markdown
# Beli staging tool

Aggregates Google Maps saved lists (→ Want to Try) and GPS-stamped photos
(→ Been) into a phone-friendly worklist for fast manual entry into Beli.
Matching uses each photo's embedded GPS coordinate (not image content) via the
Google Places API. A local SQLite ledger keeps it incremental — each run shows
only places you haven't handled yet.

## One-time setup

1. Create a free Google Places API key (Maps Platform → Places API).
2. `cp config.example.toml config.toml` and paste your key.
3. `python3 -m venv .venv && . .venv/bin/activate && pip install -e .`
4. Grant Photos access when macOS prompts on first run.

## Each run

1. Export Google Takeout → "Maps (your places)"; unzip the `Saved/*.csv` files
   into `~/beli-tool/inbox/`.
2. `beli-tool run`
3. Open the printed `http://<ip>:8000` URL on your phone (same Wi-Fi).
4. Rank each Been place (😍/😐/😞), tap "Copy & open Beli", paste, add, then
   tap "Added ✓". Tap through Want to Try the same way.

The final tap into Beli is manual by design (Beli has no import/API).
````

- [ ] **Step 3: Commit**

```bash
cd ~/beli-tool && git add README.md config.example.toml
git commit -m "docs: README and config template"
```

---

## Follow-up plan (out of scope here)

Spec §9 distribution — packaging the tool into a double-clickable macOS `.app`
(PyInstaller/py2app), auto-building it via GitHub Actions, attaching to GitHub
Releases, and a GitHub Pages download page — is a separate plan to write once
this tool runs end-to-end. Optional spec items also deferred: the Obsidian
"Beli log" mirror; the "smart add order" grouping of Been items by sentiment
(deferred because sentiment is only known after the user ranks, so it belongs in
a post-ranking review view); and resolving whether a real `beli://` deep link
exists (the web app currently attempts `beli://` and falls back to clipboard
copy).

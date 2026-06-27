# Beli Staging Tool — Design

Date: 2026-06-27
Status: Approved design, pre-implementation

## 1. Problem & goal

Manually adding restaurants to Beli is tedious. Two rich data sources already
capture where the user wants to go and where they've been:

- **Google Maps saved lists** — places they want to try.
- **Photos with GPS metadata** — places they've actually been (a photo taken at
  a restaurant is evidence of a visit).

Beli has **no public API and no import feature**, and is **iPhone-only** (no web
app, no Mac app). True zero-touch auto-upload is therefore not safely possible —
it would require reverse-engineering Beli's private API (ToS violation, fragile)
or phone-UI automation (brittle).

**Goal:** a local **staging pipeline** that does ~95% of the work — aggregate
both sources, match photos to restaurants, dedupe against what's already been
handled, and present a fast, phone-friendly worklist where each place takes a
few seconds to rank and add. The final tap into Beli stays manual by design, to
remain safe and ToS-clean.

### Non-goals (YAGNI)
- No automated writing into Beli (no private API, no UI automation).
- No image-content recognition. Matching uses the **GPS coordinate embedded in
  each photo's metadata**, not the visual content of the picture.
- No live Google Maps sync (Google exposes no personal saved-places API; refresh
  is a periodic manual Takeout export).

## 2. Source → bucket mapping

Beli has two buckets. The sources map cleanly:

| Source | Beli bucket | Notes |
|---|---|---|
| Photo with GPS at a restaurant | **Been** (needs a ranking) | clustered into one "visit" |
| Google Maps saved list entry | **Want to Try** (wishlist) | no ranking needed |

## 3. Architecture

Approach chosen: **Python pipeline + a tiny local web app** (FastAPI serving one
phone-friendly page). Python is used because [`osxphotos`](https://github.com/RhetTbull/osxphotos)
reads the Apple Photos library directly (GPS, timestamp, image) with no manual
export, and the Python geo ecosystem is strong.

Rejected alternatives: all-JavaScript/Node (no good `osxphotos` equivalent —
would force manual photo exports); Obsidian-centric (a markdown note is a poor
surface for the tap-to-rank loop on a phone). An optional Obsidian *log mirror*
is retained as a nice-to-have.

### Project location
`~/beli-tool` (home directory), **not** iCloud Drive — code, the Python venv,
and the live SQLite ledger would otherwise risk iCloud sync conflicts and
partial writes.

### Pipeline — four independently runnable stages

1. **Extract** — two collectors produce a common "raw place" record:
   - *Maps collector*: reads Google Takeout `Saved/*.csv` lists → Want-to-Try
     candidates (name + address).
   - *Photos collector*: `osxphotos` pulls photos that have a GPS stamp, clusters
     them by **location + time** (photos close in space and time = one visit),
     and selects a representative photo per cluster → Been candidates.

2. **Enrich & match** — Google Places API resolves each item to a real
   restaurant record (name, address, `place_id`, category):
   - Maps names → resolved place records.
   - Photo clusters → reverse-geocode the cluster centroid to the nearest food
     POI(s), attaching a **confidence score**. Single confident match →
     auto-accepted. Multiple eligible food POIs within a small radius (food hall
     / stacked address) → flagged "you pick." No food POI in range → dropped to
     a "review/ignore" pile (filters out non-restaurant photos).

3. **Dedupe** — a local **SQLite ledger** keyed by `place_id`. Anything already
   marked added (or previously dismissed) is filtered out, so each run surfaces
   only genuinely new places. This makes the tool incremental forever. The
   ledger starts empty (first run surfaces everything); it is not pre-seeded
   from existing Beli data.

4. **Serve** — a local FastAPI web app, reachable from the phone on the same
   Wi-Fi, showing **one place at a time**:
   - *Want-to-Try queue*: name, address, map link → [Added ✓] / [Skip].
   - *Been queue*: representative photo, name, address, date → 😍 / 😐 / 😞
     ranking, then [Added ✓]. Low-confidence photo matches show a "which place
     was this?" picker first.
   - Each action writes straight to the ledger.

### Data flow

```
Takeout CSVs ─┐
              ├─► Extract ─► Enrich & match (Google Places) ─► Dedupe (SQLite) ─► Web app ─► you rank + add in Beli
Apple Photos ─┘                                                     ▲                              │
                                                                    └──────────── ledger update ───┘
```

## 4. Components & responsibilities

| Unit | Responsibility | Depends on |
|---|---|---|
| `maps_collector` | parse Takeout CSVs → raw places | Takeout export in inbox folder |
| `photos_collector` | read Photos GPS, cluster visits, pick representative | `osxphotos` |
| `matcher` | resolve names / reverse-geocode GPS → restaurant + confidence | Google Places API key |
| `ledger` | SQLite store of handled `place_id`s; dedupe queries | sqlite3 |
| `webapp` | FastAPI server + single phone-friendly page | matched+deduped queue |
| `obsidian_log` (optional) | append added places to a vault note | Obsidian vault path |

Each unit has a clear single purpose, a defined input/output record shape, and
is testable in isolation.

## 5. Above-and-beyond touches

- **One-tap hand-off to Beli**: each card has a "copy name & open Beli" button.
  Investigate whether Beli exposes a `beli://` URL scheme; if not, fall back to
  copying the name to clipboard + opening an Apple Maps share, so the in-app
  search is paste-and-go.
- **Smart add order** for Been: group by sentiment bucket so Beli's pairwise
  comparison flow converges fast and avoids context-switching.
- **Confidence triage**: weak/no-match photos go to a separate review pile
  instead of polluting the main queue.
- *(Optional)* Obsidian "Beli log" mirror — append each added place to a vault
  note as a running history.

## 6. Setup (one-time)

1. Create a free Google Places API key; paste into a local config file.
2. Grant the tool access to the Photos library (macOS permission prompt).

## 7. Per-run flow

1. Run a Google Takeout export of "Maps (your places)," drop the zip in
   `~/beli-tool/inbox/`.
2. Run `beli-tool run`.
3. Open the printed local URL on the phone (same Wi-Fi).
4. Work the queue: rank + "copy & open Beli" + paste + [Added ✓].
5. Ledger updates; next run surfaces only new places.

## 8. Honest limitations (designed around, not bugs)

- Google Maps refresh is a **manual periodic Takeout** (no personal API). The
  tool auto-detects only-new entries once the export is dropped in.
- **Final entry is manual taps in Beli.** The tool removes the finding,
  matching, deduping, deciding, and ordering friction (~95%) but not the add
  itself.
- **Ambiguous photo matches need a glance** to confirm; the tool never silently
  guesses wrong.

## 9. Testing approach

- `maps_collector`: fixture Takeout CSVs → expected raw records.
- `photos_collector`: clustering logic tested with synthetic (lat, lon, time)
  point sets; `osxphotos` access behind a thin adapter that can be stubbed.
- `matcher`: Google Places responses mocked; assert confident vs ambiguous vs
  no-match branches.
- `ledger`: in-memory SQLite; assert dedupe filters handled `place_id`s.
- `webapp`: route tests for queue rendering and the rank/add/skip actions
  writing to the ledger.

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_HOME = Path.home() / "Library" / "Application Support" / "beli-tool"
LOG_PATH = DEFAULT_HOME / "beli-tool.log"

_TEMPLATE = """\
# Matching provider: "google" (Places API (New), needs the key below plus a
# billing account) or "osm" (OpenStreetMap via Overpass + Nominatim: free, no
# key, no billing; coverage is thinner, so more visits land in review).
provider = "google"
google_places_api_key = "PASTE_YOUR_KEY_HERE"
# Folder holding your Google Takeout "Saved/*.csv" lists.
saved_dir = "{home}/inbox"
db_path = "{home}/ledger.sqlite"
# Cap on how many photo "visits" (most recent first) to match per run.
# Each visit is one lookup (billed on "google", free on "osm"); raise this to
# process more backlog.
max_visits = 300
# Ignore photos taken before this date. Keeps the library scan bounded —
# without it every run walks your entire Photos history.
# since = "2024-01-01"
# Optional: mirror every place you add into an Obsidian note, as a running
# history. The note is created on first write. Leave unset to skip entirely.
# An iCloud vault lives under the path shape below — swap in your vault name.
# obsidian_log = "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/YOUR_VAULT/08-Lookup/beli-log.md"
"""


@dataclass
class Config:
    api_key: str
    saved_dir: Path
    db_path: Path
    provider: str = "google"
    max_visits: int = 300
    since: date | None = None
    obsidian_log: Path | None = None


def _seed_home() -> Path:
    """Create the default home + inbox + a template config.toml on first run.

    Returns the config path. This is why a fresh install lands on a
    self-explaining file to edit, not a bare error pointing at a folder that
    was never created.
    """
    DEFAULT_HOME.mkdir(parents=True, exist_ok=True)
    (DEFAULT_HOME / "inbox").mkdir(exist_ok=True)
    cfg_path = DEFAULT_HOME / "config.toml"
    if not cfg_path.exists():
        cfg_path.write_text(_TEMPLATE.format(home=DEFAULT_HOME))
    return cfg_path


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        path = _seed_home()  # default run: ensure home exists + seed a template
    else:
        path = Path(path)
    data: dict = {}
    if path.exists():
        data = tomllib.load(path.open("rb"))
    provider = str(data.get("provider", "google")).lower()
    if provider not in ("google", "osm"):
        raise RuntimeError(
            f'config: provider must be "google" or "osm", got "{provider}" in {path}'
        )
    api_key = data.get("google_places_api_key") or os.environ.get("BELI_PLACES_KEY", "")
    if provider == "google" and (not api_key or api_key == "PASTE_YOUR_KEY_HERE"):
        raise RuntimeError(
            f"Add your Google Places API key to {path}\n"
            "(or set the BELI_PLACES_KEY environment variable), then reopen.\n"
            'No Google billing account? Set provider = "osm" in the same file '
            "to match against OpenStreetMap for free instead."
        )
    saved_dir = Path(data.get("saved_dir", DEFAULT_HOME / "inbox")).expanduser()
    db_path = Path(data.get("db_path", DEFAULT_HOME / "ledger.sqlite")).expanduser()
    max_visits = int(data.get("max_visits", 300))
    raw_since = data.get("since")
    # tomllib gives a real date for an unquoted TOML date; accept a quoted
    # "YYYY-MM-DD" too, since that's the easy thing to type.
    if isinstance(raw_since, str):
        since = date.fromisoformat(raw_since)
    else:
        since = raw_since
    raw_log = data.get("obsidian_log")
    obsidian_log = Path(raw_log).expanduser() if raw_log else None
    return Config(
        api_key=api_key,
        saved_dir=saved_dir,
        db_path=db_path,
        provider=provider,
        max_visits=max_visits,
        since=since,
        obsidian_log=obsidian_log,
    )

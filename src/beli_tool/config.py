from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOME = Path.home() / "Library" / "Application Support" / "beli-tool"

_TEMPLATE = """\
google_places_api_key = "PASTE_YOUR_KEY_HERE"
# Folder holding your Google Takeout "Saved/*.csv" lists.
saved_dir = "{home}/inbox"
db_path = "{home}/ledger.sqlite"
# Cap on how many photo "visits" (most recent first) to match per run.
# Each visit costs one Google Places lookup; raise this to process more backlog.
max_visits = 300
"""


@dataclass
class Config:
    api_key: str
    saved_dir: Path
    db_path: Path
    max_visits: int = 300


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
    api_key = data.get("google_places_api_key") or os.environ.get("BELI_PLACES_KEY", "")
    if not api_key or api_key == "PASTE_YOUR_KEY_HERE":
        raise RuntimeError(
            f"Add your Google Places API key to {path}\n"
            "(or set the BELI_PLACES_KEY environment variable), then reopen."
        )
    saved_dir = Path(data.get("saved_dir", DEFAULT_HOME / "inbox")).expanduser()
    db_path = Path(data.get("db_path", DEFAULT_HOME / "ledger.sqlite")).expanduser()
    max_visits = int(data.get("max_visits", 300))
    return Config(
        api_key=api_key, saved_dir=saved_dir, db_path=db_path, max_visits=max_visits
    )

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
        data = tomllib.load(path.open("rb"))
    api_key = data.get("google_places_api_key") or os.environ.get("BELI_PLACES_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Missing Google Places API key. Set google_places_api_key in "
            "config.toml or the BELI_PLACES_KEY environment variable."
        )
    saved_dir = Path(data.get("saved_dir", DEFAULT_HOME / "inbox"))
    db_path = Path(data.get("db_path", DEFAULT_HOME / "ledger.sqlite"))
    return Config(api_key=api_key, saved_dir=saved_dir, db_path=db_path)

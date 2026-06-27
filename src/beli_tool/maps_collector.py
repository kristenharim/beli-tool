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

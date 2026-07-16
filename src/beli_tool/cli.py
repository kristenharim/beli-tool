from __future__ import annotations

import secrets
import socket
import sys
from datetime import date

import uvicorn
from fastapi import FastAPI

from beli_tool.config import Config, load_config
from beli_tool.ledger import Ledger
from beli_tool.maps_collector import collect_maps
from beli_tool.photos_collector import collect_photos
from beli_tool.photos_source import OsxPhotosSource
from beli_tool.pipeline import build_queue
from beli_tool.places_cache import PlacesCache
from beli_tool.places_client import PlacesClient
from beli_tool.webapp import create_app


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def build_app_from_config(
    cfg: Config, photo_source=None, client=None, token=None
) -> tuple[FastAPI, Ledger]:
    photo_source = photo_source or OsxPhotosSource(
        since=cfg.since,
        on_progress=lambda n: print(f"\r  scanned {n} photos…", end="", flush=True),
    )
    client = client or PlacesClient(cfg.api_key, cache=PlacesCache(cfg.db_path))
    ledger = Ledger(cfg.db_path)

    print("Reading Google Maps saved lists…", flush=True)
    maps_places = collect_maps(cfg.saved_dir)
    print(f"  {len(maps_places)} saved place(s) found.", flush=True)

    window = f" taken since {cfg.since}" if cfg.since else " (whole library — set `since` in config.toml to bound this)"
    print(f"Reading Apple Photos for GPS-tagged photos{window}…", flush=True)
    photo_raws = collect_photos(photo_source)
    print(f"\r  {len(photo_raws)} photo visit(s) found.", flush=True)

    if cfg.max_visits and len(photo_raws) > cfg.max_visits:
        photo_raws.sort(key=lambda r: r.visit_date or date.min, reverse=True)
        skipped = len(photo_raws) - cfg.max_visits
        photo_raws = photo_raws[: cfg.max_visits]
        print(
            f"  Capping at the {cfg.max_visits} most recent visits "
            f"({skipped} older skipped — raise max_visits in config.toml to include them).",
            flush=True,
        )

    total = len(maps_places) + len(photo_raws)
    print(f"Matching {total} place(s) with Google Places…", flush=True)
    queue = build_queue(
        maps_places,
        photo_raws,
        client,
        ledger,
        on_progress=lambda done, n: print(f"\r  {done}/{n}", end="", flush=True),
    )
    print(flush=True)
    hits = getattr(client, "hits", 0)
    if hits:
        print(f"  {hits} lookup(s) served from cache — no API charge.", flush=True)
    print(
        f"Ready: {len(queue.want_to_try)} to try, {len(queue.been)} been, "
        f"{len(queue.review)} unmatched.",
        flush=True,
    )
    photo_resolver = getattr(photo_source, "thumbnail_path", None)
    return create_app(queue, ledger, photo_resolver=photo_resolver, token=token), ledger


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "run":
        print("usage: beli-tool run")
        return
    cfg = load_config()
    token = secrets.token_urlsafe(8)
    app, _ = build_app_from_config(cfg, token=token)
    port = 8000
    url = f"http://{local_ip()}:{port}/?t={token}"
    print(f"\n  Beli staging ready → open  {url}  on your phone\n")
    uvicorn.run(app, host="0.0.0.0", port=port)

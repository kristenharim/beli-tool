from __future__ import annotations

import logging
import secrets
import socket
import sys
from datetime import date

import uvicorn
from fastapi import FastAPI

from beli_tool import __version__
from beli_tool.config import LOG_PATH, Config, load_config
from beli_tool.ledger import Ledger
from beli_tool.logsetup import setup_logging
from beli_tool.maps_collector import collect_maps
from beli_tool.obsidian_log import ObsidianLog
from beli_tool.osm_client import OsmClient
from beli_tool.photos_collector import collect_photos
from beli_tool.photos_source import OsxPhotosSource
from beli_tool.pipeline import Queue, build_queue
from beli_tool.places_cache import PlacesCache
from beli_tool.places_client import PlacesClient, PlacesError
from beli_tool.webapp import create_app


log = logging.getLogger(__name__)


def describe(cfg: Config) -> str:
    """One-line config summary for the log. Deliberately never includes
    api_key: the log is a plain file and the key is the one secret here."""
    return (
        f"provider={cfg.provider} since={cfg.since} max_visits={cfg.max_visits} "
        f"saved_dir={cfg.saved_dir} db={cfg.db_path} "
        f"obsidian_log={'on' if cfg.obsidian_log else 'off'}"
    )


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def scan(cfg: Config, photo_source, client, ledger: Ledger) -> Queue:
    """Collect from both sources and match them. Repeatable: /api/rescan calls
    this again on the same ledger and cache, so a rescan is cheap and picks up
    newly-added photos or CSVs without a restart."""
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
    provider_name = "OpenStreetMap" if cfg.provider == "osm" else "Google Places"
    print(f"Matching {total} place(s) with {provider_name}…", flush=True)
    log.info(
        "scan: %d saved place(s), %d photo visit(s)%s",
        len(maps_places),
        len(photo_raws),
        f" since {cfg.since}" if cfg.since else " (whole library)",
    )
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
    log.info(
        "ready: %d to try, %d been, %d unmatched (%d cached, %d billed lookups)",
        len(queue.want_to_try),
        len(queue.been),
        len(queue.review),
        hits,
        getattr(client, "calls", 0),
    )
    return queue


def build_app_from_config(
    cfg: Config, photo_source=None, client=None, token=None
) -> tuple[FastAPI, Ledger]:
    photo_source = photo_source or OsxPhotosSource(
        since=cfg.since,
        on_progress=lambda n: print(f"\r  scanned {n} photos…", end="", flush=True),
    )
    if client is None:
        cache = PlacesCache(cfg.db_path)
        if cfg.provider == "osm":
            client = OsmClient(cache=cache)
        else:
            client = PlacesClient(cfg.api_key, cache=cache)
    ledger = Ledger(cfg.db_path)

    def rebuild() -> Queue:
        return scan(cfg, photo_source, client, ledger)

    queue = rebuild()
    photo_resolver = getattr(photo_source, "thumbnail_path", None)
    obsidian_log = ObsidianLog(cfg.obsidian_log) if cfg.obsidian_log else None
    if obsidian_log:
        print(f"  Mirroring adds to {cfg.obsidian_log}", flush=True)
    app = create_app(
        queue,
        ledger,
        photo_resolver=photo_resolver,
        token=token,
        rebuild=rebuild,
        obsidian_log=obsidian_log,
    )
    return app, ledger


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "run":
        print("usage: beli-tool run")
        return
    logged_to = setup_logging(LOG_PATH)
    log.info("--- beli-tool %s starting (cli) ---", __version__)
    try:
        cfg = load_config()
    except RuntimeError as e:
        log.error("config: %s", e)
        raise
    log.info("config: %s", describe(cfg))
    token = secrets.token_urlsafe(8)
    try:
        app, _ = build_app_from_config(cfg, token=token)
    except PlacesError as e:  # setup mistake: print the fix, not a traceback
        log.error("places: %s", e)
        print(f"\n{e}\n", file=sys.stderr)
        if logged_to:
            print(f"(logged to {logged_to})", file=sys.stderr)
        raise SystemExit(1)
    port = 8000
    url = f"http://{local_ip()}:{port}/?t={token}"
    print(f"\n  Beli staging ready → open  {url}  on your phone\n")
    uvicorn.run(app, host="0.0.0.0", port=port)

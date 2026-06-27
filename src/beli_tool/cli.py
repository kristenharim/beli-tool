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
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


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

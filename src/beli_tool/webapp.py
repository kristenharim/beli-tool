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

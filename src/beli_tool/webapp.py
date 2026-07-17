from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from beli_tool import __version__
from beli_tool.ledger import Ledger
from beli_tool.models import MatchedPlace
from beli_tool.pipeline import Queue
from beli_tool.places_client import PlacesError

_INDEX = (Path(__file__).parent / "templates" / "index.html").read_text()
log = logging.getLogger(__name__)


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
        "raw_name": m.raw.name,  # search string for unmatched cards (match is None)
        "source": m.raw.source,
        "bucket": m.bucket,
        "status": m.status,
        "visit_date": vd,
        "photo_count": m.raw.photo_count,
        "photo_ref": m.raw.photo_ref,
        "photo_refs": m.raw.photo_refs,
        "candidates": [
            {"place_id": c.place_id, "name": c.name, "address": c.address}
            for c in m.candidates
        ],
    }


def _lookup(queue: Queue, place_id: str) -> tuple[str, object]:
    """Find (address, visit_date) for a place_id in the live queue.

    The client only posts place_id/name/bucket/rating, but the log wants the
    address and visit date — they're already on the server, so read them here
    rather than widening the request. Ambiguous cards resolve via candidates.
    """
    for items in (queue.want_to_try, queue.been, queue.review):
        for m in items:
            if m.match and m.match.place_id == place_id:
                return m.match.address, m.raw.visit_date
            for c in m.candidates:
                if c.place_id == place_id:
                    return c.address, m.raw.visit_date
    return "", None


def _visible(items: list[MatchedPlace], handled: set[str]) -> list[dict]:
    out = []
    for m in items:
        if m.match and m.match.place_id in handled:
            continue
        if m.candidates and any(c.place_id in handled for c in m.candidates):
            continue
        out.append(_serialize(m))
    return out


def create_app(
    queue: Queue,
    ledger: Ledger,
    photo_resolver=None,
    token=None,
    rebuild=None,
    obsidian_log=None,
) -> FastAPI:
    """photo_resolver: optional callable (uuid -> filesystem path | None) used to
    serve a card's photo thumbnail at /api/photo/{uuid}.

    token: if set, every route requires it — supplied as ``?t=<token>`` (in the
    phone URL) or the ``beli_token`` cookie that opening that URL sets. Guards
    the LAN server so a shared Wi-Fi neighbor can't read photos/location history.
    token=None disables the check (tests, localhost dev).

    rebuild: optional callable returning a fresh Queue, exposed as POST
    /api/rescan so new photos/CSVs can be picked up without quitting the app.

    obsidian_log: optional ObsidianLog; each added place is mirrored to a vault
    note. Best-effort — a vault write must never fail the ledger write.
    """
    app = FastAPI()
    # The live queue is swapped wholesale by a rescan, so route handlers read
    # through this holder rather than closing over the original object.
    state = {"queue": queue}
    rescan_lock = threading.Lock()

    def guard(request: Request) -> None:
        if token is None:
            return
        supplied = request.query_params.get("t") or request.cookies.get("beli_token")
        if supplied != token:
            raise HTTPException(status_code=403, detail="bad or missing token")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        guard(request)  # first load must carry ?t=; then the cookie takes over
        resp = HTMLResponse(_INDEX)
        if token is not None:
            resp.set_cookie("beli_token", token, httponly=True, samesite="lax")
        return resp

    @app.get("/api/photo/{uuid}")
    def photo(uuid: str, _=Depends(guard)):
        path = photo_resolver(uuid) if photo_resolver else None
        if not path:
            return Response(status_code=404)
        return FileResponse(path)

    @app.get("/api/queue")
    def get_queue(_=Depends(guard)) -> dict:
        handled = ledger.handled_ids()
        q = state["queue"]
        return {
            "version": __version__,
            "can_rescan": rebuild is not None,
            "want_to_try": _visible(q.want_to_try, handled),
            "been": _visible(q.been, handled),
            "review": _visible(q.review, handled),
        }

    @app.post("/api/rescan")
    def rescan(_=Depends(guard)) -> dict:
        if rebuild is None:
            raise HTTPException(status_code=501, detail="rescan unavailable")
        # Non-blocking: a double-tap must not run two scans at once — they'd
        # race on the shared photo source's uuid index.
        if not rescan_lock.acquire(blocking=False):
            log.info("rescan rejected: one already running")
            raise HTTPException(status_code=409, detail="a rescan is already running")
        try:
            log.info("rescan requested")
            state["queue"] = rebuild()
        except PlacesError as e:
            log.error("rescan failed: %s", e)
            raise HTTPException(status_code=502, detail=str(e))
        finally:
            rescan_lock.release()
        return {"ok": True}

    @app.post("/api/added")
    def added(req: AddedReq, _=Depends(guard)) -> dict:
        # Ledger first: it's the source of truth, the vault note is the mirror.
        ledger.mark_added(req.place_id, req.name, req.bucket, req.rating)
        log.info(
            "added: %s (%s) rating=%s id=%s",
            req.name, req.bucket, req.rating or "-", req.place_id,
        )
        if obsidian_log is not None:
            address, visit_date = _lookup(state["queue"], req.place_id)
            if not obsidian_log.append(
                req.name, req.bucket, req.rating, address=address, visit_date=visit_date
            ):
                # The add itself stands; only the mirror line was lost.
                log.warning("obsidian log write failed for %s", req.name)
        return {"ok": True}

    @app.post("/api/skip")
    def skip(req: SkipReq, _=Depends(guard)) -> dict:
        ledger.mark_dismissed(req.place_id, req.name, req.bucket)
        log.info("skipped: %s id=%s", req.name or "-", req.place_id)
        return {"ok": True}

    return app

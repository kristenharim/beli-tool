"""Double-click .app entry point.

Runs the same pipeline as `beli-tool run`, but surfaces progress, the phone URL,
and any setup error through native dialogs/notifications instead of a terminal
(the .app is windowed, so there is no console to read).
"""
from __future__ import annotations

import logging
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import uvicorn

from beli_tool import __version__
from beli_tool.cli import build_app_from_config, describe, local_ip
from beli_tool.config import LOG_PATH, load_config
from beli_tool.logsetup import setup_logging
from beli_tool.photos_source import OsxPhotosSource
from beli_tool.places_client import PlacesError

PORT = 8000
log = logging.getLogger("beli_tool.app_entry")


def _app_path() -> str:
    """Best-effort path to the .app bundle, for the Full Disk Access dialog."""
    p = sys.executable
    i = p.find(".app/")
    return p[: i + 4] if i != -1 else p


def _q(text: str) -> str:
    # AppleScript string literal: double-quoted, with \ " and newline escaped.
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def notify(text: str) -> None:  # non-blocking banner
    subprocess.run(
        ["osascript", "-e", f'display notification "{_q(text)}" with title "Beli staging"'],
        check=False,
    )


def dialog(text: str) -> None:  # blocking, needs a click
    subprocess.run(
        ["osascript", "-e",
         f'display dialog "{_q(text)}" with title "Beli staging" buttons {{"OK"}} default button "OK"'],
        check=False,
    )


def announce_when_ready(url: str) -> None:
    for _ in range(120):  # wait up to ~60s for uvicorn to accept connections
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                break
        except OSError:
            time.sleep(0.5)
    webbrowser.open(url)  # desktop convenience (carries the ?t= token)
    dialog(f"Beli is running.\n\nOn your phone, open:\n{url}\n\nQuit this app when you're done.")


def main() -> None:
    setup_logging(LOG_PATH)
    log.info("--- beli-tool %s starting (.app) ---", __version__)
    try:
        cfg = load_config()
    except Exception as e:  # missing key / config: tell the user, don't die silently
        log.error("config: %s", e)
        dialog(f"Setup needed:\n\n{e}")
        return
    log.info("config: %s", describe(cfg))

    # probe() opens the Photos library, which is the slow part: say so first,
    # or the app sits silent through it.
    notify("Opening your Photos library… this can take a minute.")

    # Full Disk Access has no system prompt: check before the long scan so a
    # denial becomes a clear instruction, not a silent hang or crash.
    source = OsxPhotosSource(since=cfg.since)
    probe_error = source.probe()
    if probe_error is not None:
        log.error("photos library unreadable (likely Full Disk Access): %s", probe_error)
        dialog(
            "Beli needs Full Disk Access to read your Photos library.\n\n"
            "Open System Settings → Privacy & Security → Full Disk Access, turn "
            f"on:\n{_app_path()}\n\nThen reopen Beli staging."
        )
        return

    notify("Matching your places… almost there.")
    token = secrets.token_urlsafe(8)
    try:
        app, _ = build_app_from_config(cfg, photo_source=source, token=token)
    except PlacesError as e:  # key/billing/quota: show the fix, not a stack trace
        log.error("places: %s", e)
        dialog(str(e))
        return
    except Exception:
        # Windowed app: an uncaught traceback would vanish entirely. Record it,
        # then say where to look.
        log.exception("unexpected failure while building the worklist")
        dialog(f"Something went wrong.\n\nDetails were written to:\n{LOG_PATH}")
        return
    url = f"http://{local_ip()}:{PORT}/?t={token}"
    log.info("serving on %s", url.split("?")[0])  # no token in the log
    threading.Thread(target=announce_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")  # blocks, keeps app alive


if __name__ == "__main__":
    main()

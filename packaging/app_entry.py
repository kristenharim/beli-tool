"""Double-click .app entry point.

Runs the same pipeline as `beli-tool run`, but surfaces progress, the phone URL,
and any setup error through native dialogs/notifications instead of a terminal
(the .app is windowed, so there is no console to read).
"""
from __future__ import annotations

import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import uvicorn

from beli_tool.cli import build_app_from_config, local_ip
from beli_tool.config import load_config
from beli_tool.photos_source import OsxPhotosSource

PORT = 8000


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
    try:
        cfg = load_config()
    except Exception as e:  # missing key / config — tell the user, don't die silently
        dialog(f"Setup needed:\n\n{e}")
        return

    # probe() opens the Photos library, which is the slow part — say so first,
    # or the app sits silent through it.
    notify("Opening your Photos library… this can take a minute.")

    # Full Disk Access has no system prompt — check before the long scan so a
    # denial becomes a clear instruction, not a silent hang or crash.
    source = OsxPhotosSource(since=cfg.since)
    if source.probe() is not None:
        dialog(
            "Beli needs Full Disk Access to read your Photos library.\n\n"
            "Open System Settings → Privacy & Security → Full Disk Access, turn "
            f"on:\n{_app_path()}\n\nThen reopen Beli staging."
        )
        return

    notify("Matching your places… almost there.")
    token = secrets.token_urlsafe(8)
    app, _ = build_app_from_config(cfg, photo_source=source, token=token)
    url = f"http://{local_ip()}:{PORT}/?t={token}"
    threading.Thread(target=announce_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")  # blocks, keeps app alive


if __name__ == "__main__":
    main()

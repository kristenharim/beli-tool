from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_MAX_BYTES = 512_000  # ~a few thousand runs' worth; rotation keeps it bounded
_BACKUPS = 2

# Everything under beli_tool.* inherits from this one, so modules just do
# logging.getLogger(__name__) and land here without extra wiring.
ROOT = "beli_tool"


def setup_logging(path: str | Path, level: int = logging.INFO) -> Path | None:
    """Send the log to a rotating file. Returns the path, or None on failure.

    The .app is windowed: every print() in it goes to a stdout nobody will ever
    read, so when something misbehaves months from now this file is the only
    account of what happened.

    Never fatal: not being able to open a log is not a reason to refuse to run.
    """
    path = Path(path).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
    except OSError:
        return None
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    log = logging.getLogger(ROOT)
    log.setLevel(level)
    # Idempotent: a second call (rescan, tests, a re-entered main) must not
    # attach a second handler and double every line from then on.
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()
    log.addHandler(handler)
    return path

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path


class PlacesCache:
    """SQLite cache of Google Places responses, keyed by request signature.

    Deliberately separate from the handled ledger: the ledger records what you
    acted on, this records what Google answered. Without it, every run
    re-queries (and re-bills) every place you haven't handled yet, forever.

    Empty responses are cached too: a place that matched nothing is exactly the
    one that would otherwise be paid for on every single run.
    """

    def __init__(self, db_path: str | Path = ":memory:", ttl_days: int = 90):
        # Same invariant as Ledger: every self.conn access MUST hold self._lock.
        self._lock = threading.Lock()
        self._ttl_days = ttl_days
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        with self._lock:
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS places_cache (
                    key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    ts TEXT DEFAULT (datetime('now'))
                )"""
            )
            self.conn.commit()

    def get(self, key: str) -> list[dict] | None:
        """Cached response, or None on miss/expiry. Restaurants close, so
        entries older than ttl_days are treated as misses."""
        with self._lock:
            row = self.conn.execute(
                "SELECT response FROM places_cache "
                "WHERE key = ? AND ts > datetime('now', ?)",
                (key, f"-{self._ttl_days} days"),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: list[dict]) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT INTO places_cache (key, response) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                     response=excluded.response, ts=datetime('now')""",
                (key, json.dumps(value)),
            )
            self.conn.commit()

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class Ledger:
    def __init__(self, db_path: str | Path = ":memory:"):
        # Invariant: every access to self.conn MUST hold self._lock (check_same_thread=False removes sqlite's own guard).
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        with self._lock:
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS handled (
                    place_id TEXT PRIMARY KEY,
                    name TEXT,
                    bucket TEXT,
                    rating TEXT,
                    action TEXT,
                    ts TEXT DEFAULT (datetime('now'))
                )"""
            )
            self.conn.commit()

    def handled_ids(self) -> set[str]:
        with self._lock:
            return {row[0] for row in self.conn.execute("SELECT place_id FROM handled")}

    def is_handled(self, place_id: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "SELECT 1 FROM handled WHERE place_id = ?", (place_id,)
            )
            return cur.fetchone() is not None

    def _upsert(self, place_id, name, bucket, rating, action) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT INTO handled (place_id, name, bucket, rating, action)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(place_id) DO UPDATE SET
                     name=excluded.name, bucket=excluded.bucket,
                     rating=excluded.rating, action=excluded.action,
                     ts=datetime('now')""",
                (place_id, name, bucket, rating, action),
            )
            self.conn.commit()

    def mark_added(self, place_id, name, bucket, rating=None) -> None:
        self._upsert(place_id, name, bucket, rating, "added")

    def mark_dismissed(self, place_id, name="", bucket="") -> None:
        self._upsert(place_id, name, bucket, None, "dismissed")

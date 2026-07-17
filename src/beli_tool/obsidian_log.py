from __future__ import annotations

from datetime import date
from pathlib import Path

_RATING_EMOJI = {"loved": "😍 loved", "fine": "😐 fine", "disliked": "😞 disliked"}

# The table lives at the end so appends are a plain write — no parsing, no
# rewriting the file. That's why "When to use" precedes "Content" here, unlike
# the vault's usual reference-note order.
_HEADER = """\
---
type: reference
ref-kind: places
tags: [food, beli, log]
created: {today}
---

# Beli log

## Summary
Running history of every place added to Beli via `beli-tool`. Append-only mirror
of the tool's ledger — the ledger (`ledger.sqlite`) stays the source of truth,
this is the readable copy that survives it.

## When to use
"Where have I eaten and what did I think of it?" — or reconstructing what was
already added if the ledger is ever lost.

## Content

| Added | Place | Rating | Visited | Address | List |
|:--|:--|:--|:--|:--|:--|
"""


def _cell(text: str) -> str:
    """Make a value safe inside a markdown table cell.

    A literal | ends the cell and silently breaks the row — the vault's own
    formatting rule calls this out, and restaurant names really do contain one.
    """
    return (text or "").replace("|", "\\|").replace("\n", " ").strip() or "—"


class ObsidianLog:
    """Appends each added place to a note in the Obsidian vault.

    Best-effort by design: the vault lives in iCloud and may be mid-sync, absent,
    or read-only. A logging failure must never lose the ledger write it mirrors,
    so every error is swallowed — the ledger already recorded the truth.
    """

    def __init__(self, path: str | Path, today=date.today):
        self.path = Path(path).expanduser()
        self._today = today

    def append(
        self,
        name: str,
        bucket: str,
        rating: str | None = None,
        address: str = "",
        visit_date: date | None = None,
    ) -> bool:
        """Append one row. Returns True if written, False if it couldn't be."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self.path.write_text(_HEADER.format(today=self._today().isoformat()))
            row = (
                f"| {self._today().isoformat()} "
                f"| {_cell(name)} "
                f"| {_cell(_RATING_EMOJI.get(rating or '', ''))} "
                f"| {_cell(visit_date.isoformat() if visit_date else '')} "
                f"| {_cell(address)} "
                f"| {_cell('Been' if bucket == 'been' else 'Want to try')} |\n"
            )
            with self.path.open("a", encoding="utf-8") as f:
                f.write(row)
            return True
        except OSError:
            return False

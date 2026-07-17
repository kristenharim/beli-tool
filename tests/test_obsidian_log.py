import re
from datetime import date

from beli_tool.obsidian_log import ObsidianLog

FIXED = lambda: date(2026, 7, 16)  # noqa: E731


def _log(tmp_path, name="beli-log.md"):
    return ObsidianLog(tmp_path / name, today=FIXED)


def _rows(path):
    return [l for l in path.read_text().splitlines() if l.startswith("| 2026-")]


def test_creates_the_note_with_frontmatter_and_table_header(tmp_path):
    log = _log(tmp_path)
    assert log.append("Lilia", "been", "loved", address="567 Union Ave") is True
    text = log.path.read_text()
    assert text.startswith("---\ntype: reference\n")
    assert "ref-kind: places" in text
    assert "# Beli log" in text
    assert "| Added | Place | Rating | Visited | Address | List |" in text


def test_appends_a_row_per_add(tmp_path):
    log = _log(tmp_path)
    log.append("Lilia", "been", "loved", address="567 Union Ave", visit_date=date(2026, 4, 12))
    log.append("Dhamaka", "want_to_try", address="119 Delancey")
    rows = _rows(log.path)
    assert len(rows) == 2
    assert "Lilia" in rows[0] and "😍 loved" in rows[0] and "2026-04-12" in rows[0]
    assert "Been" in rows[0]
    assert "Dhamaka" in rows[1] and "Want to try" in rows[1]


def test_header_written_once_not_per_row(tmp_path):
    log = _log(tmp_path)
    log.append("Lilia", "been", "loved")
    log.append("Dhamaka", "want_to_try")
    assert log.path.read_text().count("# Beli log") == 1


def test_survives_a_restart(tmp_path):
    _log(tmp_path).append("Lilia", "been", "loved")
    _log(tmp_path).append("Dhamaka", "want_to_try")  # fresh instance, same note
    assert len(_rows(tmp_path / "beli-log.md")) == 2


def test_pipe_in_a_name_is_escaped_and_row_still_parses(tmp_path):
    # A literal | ends the cell and silently breaks the row — the vault's own
    # formatting rule calls this out, and restaurant names do contain them.
    log = _log(tmp_path)
    log.append("Wine | Bar", "been", "fine", address="1 A St")
    row = _rows(log.path)[0]
    assert r"Wine \| Bar" in row
    # The invariant that matters: still 6 cells when split on unescaped pipes.
    cells = re.split(r"(?<!\\)\|", row)
    assert len(cells) == 8  # leading '' + 6 cells + trailing ''
    assert cells[2].strip() == r"Wine \| Bar"


def test_missing_optional_fields_render_as_dashes(tmp_path):
    log = _log(tmp_path)
    log.append("Dhamaka", "want_to_try")  # no rating, address, or visit date
    assert "| — |" in _rows(log.path)[0]


def test_creates_missing_parent_directories(tmp_path):
    log = ObsidianLog(tmp_path / "vault" / "08-Lookup" / "beli-log.md", today=FIXED)
    assert log.append("Lilia", "been", "loved") is True
    assert log.path.exists()


def test_unwritable_vault_returns_false_without_raising(tmp_path):
    # The vault is in iCloud and may be absent or mid-sync. Losing a log line is
    # acceptable; failing the ledger write it mirrors is not.
    target = tmp_path / "ro" / "beli-log.md"
    target.parent.mkdir()
    target.parent.chmod(0o500)
    try:
        assert _log(target.parent) is not None
        assert ObsidianLog(target, today=FIXED).append("Lilia", "been", "loved") is False
    finally:
        target.parent.chmod(0o700)  # let tmp_path clean up

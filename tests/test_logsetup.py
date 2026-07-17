import logging
from datetime import date
from pathlib import Path

from beli_tool.cli import describe
from beli_tool.config import Config
from beli_tool.logsetup import ROOT, setup_logging


def _reset():
    lg = logging.getLogger(ROOT)
    for h in list(lg.handlers):
        lg.removeHandler(h)
        h.close()


def test_writes_module_logs_to_the_file(tmp_path):
    p = setup_logging(tmp_path / "beli-tool.log")
    try:
        logging.getLogger("beli_tool.webapp").info("added: Lilia")
        assert "added: Lilia" in Path(p).read_text()
        assert "beli_tool.webapp" in Path(p).read_text()
    finally:
        _reset()


def test_creates_missing_parent_directory(tmp_path):
    p = setup_logging(tmp_path / "new" / "dir" / "beli-tool.log")
    try:
        assert p is not None and Path(p).exists()
    finally:
        _reset()


def test_calling_twice_does_not_double_every_line(tmp_path):
    path = tmp_path / "beli-tool.log"
    setup_logging(path)
    setup_logging(path)  # a re-entered main / rescan must not duplicate output
    try:
        logging.getLogger("beli_tool.cli").info("once")
        assert Path(path).read_text().count("once") == 1
    finally:
        _reset()


def test_unwritable_path_returns_none_and_does_not_raise(tmp_path):
    # Not being able to log is never a reason to refuse to run.
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        assert setup_logging(ro / "sub" / "beli-tool.log") is None
    finally:
        ro.chmod(0o700)
        _reset()


def test_config_summary_never_leaks_the_api_key():
    # The log is a plain file on disk; the key is the one secret in the config.
    cfg = Config(
        api_key="AIzaSy-SUPER-SECRET-KEY",
        saved_dir=Path("/tmp/inbox"),
        db_path=Path("/tmp/l.sqlite"),
        since=date(2024, 1, 1),
        obsidian_log=Path("/tmp/beli-log.md"),
    )
    summary = describe(cfg)
    assert "AIzaSy-SUPER-SECRET-KEY" not in summary
    assert "SECRET" not in summary
    assert "since=2024-01-01" in summary  # the useful parts are still there
    assert "obsidian_log=on" in summary

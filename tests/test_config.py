from pathlib import Path

import pytest
from beli_tool.config import load_config


def test_load_config_reads_toml(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('google_places_api_key = "KEY123"\n')
    cfg = load_config(cfg_file)
    assert cfg.api_key == "KEY123"
    assert cfg.saved_dir.name == "inbox"


def test_load_config_missing_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("BELI_PLACES_KEY", raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("saved_dir = \"/tmp/x\"\n")
    with pytest.raises(RuntimeError):
        load_config(cfg_file)


def test_load_config_env_var_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("BELI_PLACES_KEY", "ENVKEY")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("saved_dir = \"/tmp/x\"\n")
    cfg = load_config(cfg_file)
    assert cfg.api_key == "ENVKEY"


def test_load_config_expands_tilde_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("BELI_PLACES_KEY", "K")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('saved_dir = "~/beli-tool/inbox"\ndb_path = "~/x.sqlite"\n')
    cfg = load_config(cfg_file)
    assert cfg.saved_dir == Path("~/beli-tool/inbox").expanduser()
    assert cfg.db_path == Path("~/x.sqlite").expanduser()
    assert "~" not in str(cfg.saved_dir)

from datetime import date
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


def test_load_config_since_defaults_to_none(tmp_path, monkeypatch):
    monkeypatch.setenv("BELI_PLACES_KEY", "K")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('saved_dir = "/tmp/x"\n')
    assert load_config(cfg_file).since is None


def test_load_config_since_accepts_quoted_and_bare_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("BELI_PLACES_KEY", "K")
    quoted = tmp_path / "q.toml"
    quoted.write_text('since = "2024-01-01"\n')
    assert load_config(quoted).since == date(2024, 1, 1)
    bare = tmp_path / "b.toml"  # tomllib parses this into a real date object
    bare.write_text("since = 2024-01-01\n")
    assert load_config(bare).since == date(2024, 1, 1)


def test_load_config_seeds_template_on_default_path(tmp_path, monkeypatch):
    monkeypatch.delenv("BELI_PLACES_KEY", raising=False)
    monkeypatch.setattr("beli_tool.config.DEFAULT_HOME", tmp_path / "home")
    # No key yet, so it still raises — but it must have created a usable home.
    with pytest.raises(RuntimeError):
        load_config()
    seeded = tmp_path / "home" / "config.toml"
    assert seeded.exists()
    assert "PASTE_YOUR_KEY_HERE" in seeded.read_text()
    assert (tmp_path / "home" / "inbox").is_dir()


def test_load_config_placeholder_key_still_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("BELI_PLACES_KEY", raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('google_places_api_key = "PASTE_YOUR_KEY_HERE"\n')
    with pytest.raises(RuntimeError):
        load_config(cfg_file)


def test_load_config_max_visits_default_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("BELI_PLACES_KEY", "K")
    default = tmp_path / "a.toml"
    default.write_text('saved_dir = "/tmp/x"\n')
    assert load_config(default).max_visits == 300
    override = tmp_path / "b.toml"
    override.write_text('saved_dir = "/tmp/x"\nmax_visits = 50\n')
    assert load_config(override).max_visits == 50

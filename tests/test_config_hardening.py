import json
from pathlib import Path

import src.logic.config as config_module


def _reset(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        config_module, "CONFIG_FILE", str(tmp_path / "config.json")
    )
    monkeypatch.setattr(config_module, "keyring", None)
    config_module.ConfigManager._reset_for_tests()


def test_defaults_are_not_shared(monkeypatch, tmp_path):
    _reset(tmp_path, monkeypatch)
    manager = config_module.ConfigManager()
    manager._config["url_fallbacks"]["x"] = "https://example.com"
    assert "x" not in config_module.DEFAULT_CONFIG["url_fallbacks"]


def test_save_replaces_valid_json_atomically(monkeypatch, tmp_path):
    _reset(tmp_path, monkeypatch)
    manager = config_module.ConfigManager()
    manager.set("auto_detective", False)
    payload = json.loads((tmp_path / "config.json").read_text())
    assert payload["auto_detective"] is False
    assert list(tmp_path.glob("config.json.tmp.*")) == []


def test_bad_config_restores_deep_defaults(monkeypatch, tmp_path):
    _reset(tmp_path, monkeypatch)
    Path(config_module.CONFIG_FILE).write_text("[]", encoding="utf-8")
    manager = config_module.ConfigManager()
    assert manager.auto_detective is True
    assert manager.url_fallbacks == config_module.DEFAULT_CONFIG["url_fallbacks"]

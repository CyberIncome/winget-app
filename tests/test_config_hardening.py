import json
from pathlib import Path

import src.logic.config as config_module


def _reset(tmp_path, monkeypatch, keyring=None):
    monkeypatch.setattr(config_module, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        config_module, "CONFIG_FILE", str(tmp_path / "config.json")
    )
    monkeypatch.setattr(config_module, "keyring", keyring)
    config_module.ConfigManager._reset_for_tests()


class FakeKeyring:
    class errors:
        class PasswordDeleteError(Exception):
            pass

    def __init__(self, fail_set=False):
        self.fail_set = fail_set
        self.values = {}

    def set_password(self, service, name, value):
        if self.fail_set:
            raise RuntimeError("credential store unavailable")
        self.values[(service, name)] = value

    def get_password(self, service, name):
        return self.values.get((service, name))

    def delete_password(self, service, name):
        key = (service, name)
        if key not in self.values:
            raise self.errors.PasswordDeleteError()
        del self.values[key]


def test_defaults_are_not_shared(monkeypatch, tmp_path):
    _reset(tmp_path, monkeypatch)
    manager = config_module.ConfigManager()
    manager._config["url_fallbacks"]["x"] = "https://example.com"
    assert "x" not in config_module.DEFAULT_CONFIG["url_fallbacks"]


def test_get_returns_copy_for_nested_values(monkeypatch, tmp_path):
    _reset(tmp_path, monkeypatch)
    manager = config_module.ConfigManager()
    fallbacks = manager.get("url_fallbacks")
    fallbacks["x"] = "https://example.com"
    assert "x" not in manager.url_fallbacks


def test_save_replaces_valid_json_atomically(monkeypatch, tmp_path):
    _reset(tmp_path, monkeypatch)
    manager = config_module.ConfigManager()
    manager.set("auto_detective", False)
    payload = json.loads((tmp_path / "config.json").read_text())
    assert payload["auto_detective"] is False
    assert list(tmp_path.glob("config.json.tmp.*")) == []


def test_bad_config_is_quarantined_and_replaced(monkeypatch, tmp_path):
    _reset(tmp_path, monkeypatch)
    Path(config_module.CONFIG_FILE).write_text("[]", encoding="utf-8")
    manager = config_module.ConfigManager()
    assert manager.auto_detective is True
    assert manager.url_fallbacks == config_module.DEFAULT_CONFIG["url_fallbacks"]
    replacement = json.loads(Path(config_module.CONFIG_FILE).read_text())
    assert replacement == config_module.DEFAULT_CONFIG
    quarantined = list(tmp_path.glob("config.json.corrupt.*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "[]"


def test_successful_legacy_pat_migration_removes_plaintext(
    monkeypatch, tmp_path
):
    fake_keyring = FakeKeyring()
    _reset(tmp_path, monkeypatch, fake_keyring)
    Path(config_module.CONFIG_FILE).write_text(
        json.dumps({"github_pat": "ghp_secret", "auto_detective": False}),
        encoding="utf-8",
    )
    manager = config_module.ConfigManager()
    assert manager.github_pat == "ghp_secret"
    payload = json.loads(Path(config_module.CONFIG_FILE).read_text())
    assert "github_pat" not in payload
    assert payload["auto_detective"] is False


def test_failed_legacy_pat_migration_keeps_original_for_retry(
    monkeypatch, tmp_path
):
    fake_keyring = FakeKeyring(fail_set=True)
    _reset(tmp_path, monkeypatch, fake_keyring)
    original = {"github_pat": "ghp_secret", "auto_detective": False}
    Path(config_module.CONFIG_FILE).write_text(
        json.dumps(original), encoding="utf-8"
    )
    manager = config_module.ConfigManager()
    assert manager.auto_detective is False
    persisted = json.loads(Path(config_module.CONFIG_FILE).read_text())
    assert persisted == original

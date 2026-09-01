"""Persistent configuration and credential storage."""

from __future__ import annotations

from copy import deepcopy
import json
import logging
import os
import threading

try:
    import keyring
except ImportError:
    keyring = None


CONFIG_DIR = os.path.join(
    os.getenv("APPDATA", os.path.expanduser("~")),
    "WingetUniversalDashboard",
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "auto_detective": True,
    "url_fallbacks": {
        "gimp": "https://github.com/GNOME/gimp/releases",
    },
}


class ConfigManager:
    """Manage persistent settings and the GitHub PAT credential."""

    _instance = None
    _lock = threading.Lock()
    _config: dict = deepcopy(DEFAULT_CONFIG)

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._config = deepcopy(DEFAULT_CONFIG)
                cls._instance.load()
        return cls._instance

    @classmethod
    def _reset_for_tests(cls):
        """Reset singleton state for isolated tests."""
        with cls._lock:
            cls._instance = None
            cls._config = deepcopy(DEFAULT_CONFIG)

    def load(self):
        """Load config from disk, preserving defaults for missing keys."""
        if not os.path.exists(CONFIG_FILE):
            self.save()
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as file_handle:
                loaded = json.load(file_handle)
            if not isinstance(loaded, dict):
                raise ValueError("config root must be a JSON object")

            legacy_pat = loaded.pop("github_pat", None)
            if legacy_pat and keyring:
                try:
                    keyring.set_password(
                        "WingetUniversalDashboard",
                        "github_pat",
                        legacy_pat,
                    )
                    logging.info("Migrated PAT to secure storage.")
                except Exception as exc:
                    logging.error("Migration failed: %s", exc)

            merged = deepcopy(DEFAULT_CONFIG)
            for key, value in loaded.items():
                merged[key] = deepcopy(value)
            if not isinstance(merged.get("url_fallbacks"), dict):
                logging.warning(
                    "Invalid url_fallbacks config; restoring defaults."
                )
                merged["url_fallbacks"] = deepcopy(
                    DEFAULT_CONFIG["url_fallbacks"]
                )
            self._config = merged
        except Exception as exc:
            logging.error(
                "Failed to load config, using defaults: %s", exc
            )
            self._config = deepcopy(DEFAULT_CONFIG)

    def save(self):
        """Atomically save config so interruption cannot leave partial JSON."""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        temp_file = (
            f"{CONFIG_FILE}.tmp.{os.getpid()}.{threading.get_ident()}"
        )
        try:
            with open(temp_file, "w", encoding="utf-8") as file_handle:
                json.dump(self._config, file_handle, indent=4)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            os.replace(temp_file, CONFIG_FILE)
        except Exception as exc:
            logging.error("Failed to save config: %s", exc)
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError:
                pass

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._config[key] = deepcopy(value)
            self.save()

    @property
    def github_pat(self):
        """Securely fetch the PAT from the OS credential store."""
        if keyring:
            try:
                pat = keyring.get_password(
                    "WingetUniversalDashboard", "github_pat"
                )
                return pat or ""
            except Exception as exc:
                logging.error("Keyring access error: %s", exc)
        return ""

    @github_pat.setter
    def github_pat(self, value):
        """Securely store the PAT in the OS credential store."""
        if not keyring:
            return
        try:
            if value:
                keyring.set_password(
                    "WingetUniversalDashboard", "github_pat", value
                )
            else:
                try:
                    keyring.delete_password(
                        "WingetUniversalDashboard", "github_pat"
                    )
                except keyring.errors.PasswordDeleteError:
                    pass
        except Exception as exc:
            logging.error("Keyring save error: %s", exc)

    @property
    def auto_detective(self):
        return bool(self.get("auto_detective", True))

    @property
    def url_fallbacks(self):
        value = self.get("url_fallbacks")
        if not isinstance(value, dict):
            return deepcopy(DEFAULT_CONFIG["url_fallbacks"])
        return deepcopy(value)

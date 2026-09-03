"""Persistent configuration and credential storage."""

from __future__ import annotations

from copy import deepcopy
import json
import logging
import os
import threading
import time

from src.logic.update_policy import normalize_ignored_updates

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
    "check_app_updates": True,
    "confirm_updates": True,
    "ignored_updates": [],
    "url_fallbacks": {
        "gimp": "https://github.com/GNOME/gimp/releases",
    },
}


class ConfigManager:
    """Manage persistent settings and the GitHub PAT credential."""

    _instance = None
    _lock = threading.RLock()
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
        """Load config, migrate secrets, and recover corrupt JSON."""
        with self._lock:
            if not os.path.exists(CONFIG_FILE):
                self._config = deepcopy(DEFAULT_CONFIG)
                self.save()
                return

            try:
                with open(
                    CONFIG_FILE, "r", encoding="utf-8"
                ) as file_handle:
                    loaded = json.load(file_handle)
                if not isinstance(loaded, dict):
                    raise ValueError("config root must be a JSON object")
            except Exception as exc:
                logging.error(
                    "Failed to load config, restoring defaults: %s", exc
                )
                self._config = deepcopy(DEFAULT_CONFIG)
                self._quarantine_corrupt_config()
                self.save()
                return

            legacy_present = "github_pat" in loaded
            legacy_pat = loaded.pop("github_pat", None)
            migration_complete = legacy_present and not legacy_pat
            if legacy_pat:
                if keyring:
                    try:
                        keyring.set_password(
                            "WingetUniversalDashboard",
                            "github_pat",
                            legacy_pat,
                        )
                        migration_complete = True
                        logging.info(
                            "Migrated legacy PAT to secure storage."
                        )
                    except Exception as exc:
                        logging.error(
                            "PAT migration failed; leaving the original "
                            "config file untouched for retry: %s",
                            exc,
                        )
                else:
                    logging.warning(
                        "Legacy PAT found but keyring is unavailable; "
                        "leaving the original config file untouched for retry."
                    )

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
            merged["ignored_updates"] = normalize_ignored_updates(
                merged.get("ignored_updates")
            )
            merged["auto_detective"] = bool(merged.get("auto_detective", True))
            merged["check_app_updates"] = bool(
                merged.get("check_app_updates", True)
            )
            merged["confirm_updates"] = bool(
                merged.get("confirm_updates", True)
            )
            self._config = merged

            if migration_complete:
                self.save()

    def _quarantine_corrupt_config(self):
        """Move unreadable config aside before writing clean defaults."""
        if not os.path.exists(CONFIG_FILE):
            return
        suffix = f"{int(time.time())}.{os.getpid()}"
        corrupt_path = f"{CONFIG_FILE}.corrupt.{suffix}"
        try:
            os.replace(CONFIG_FILE, corrupt_path)
            logging.warning(
                "Moved corrupt config to %s", corrupt_path
            )
        except OSError as exc:
            logging.error(
                "Could not quarantine corrupt config: %s", exc
            )

    def save(self):
        """Atomically save config so interruption cannot leave partial JSON."""
        with self._lock:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            temp_file = (
                f"{CONFIG_FILE}.tmp.{os.getpid()}."
                f"{threading.get_ident()}"
            )
            try:
                with open(
                    temp_file, "w", encoding="utf-8"
                ) as file_handle:
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
        with self._lock:
            return deepcopy(self._config.get(key, default))

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
            logging.warning(
                "Cannot store GitHub PAT because keyring is unavailable."
            )
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

    @auto_detective.setter
    def auto_detective(self, value):
        self.set("auto_detective", bool(value))

    @property
    def check_app_updates(self):
        return bool(self.get("check_app_updates", True))

    @check_app_updates.setter
    def check_app_updates(self, value):
        self.set("check_app_updates", bool(value))

    @property
    def confirm_updates(self):
        return bool(self.get("confirm_updates", True))

    @confirm_updates.setter
    def confirm_updates(self, value):
        self.set("confirm_updates", bool(value))

    @property
    def ignored_updates(self):
        return normalize_ignored_updates(self.get("ignored_updates", []))

    def ignore_update(self, identity: str) -> bool:
        normalized = normalize_ignored_updates(
            [*self.ignored_updates, identity]
        )
        if normalized == self.ignored_updates:
            return False
        self.set("ignored_updates", normalized)
        return True

    def clear_ignored_updates(self):
        self.set("ignored_updates", [])

    @property
    def url_fallbacks(self):
        value = self.get("url_fallbacks")
        if not isinstance(value, dict):
            return deepcopy(DEFAULT_CONFIG["url_fallbacks"])
        return value

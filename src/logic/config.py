import os
import json
import logging
import threading

try:
    import keyring
except ImportError:
    keyring = None

# Path to store the app's configuration
CONFIG_DIR = os.path.join(
    os.getenv("APPDATA", os.path.expanduser("~")),
    "WingetUniversalDashboard"
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# Default configuration (PAT moved to keyring)
DEFAULT_CONFIG = {
    "auto_detective": True,
    "url_fallbacks": {
        "gimp": "https://github.com/GNOME/gimp/releases"
    }
}

class ConfigManager:
    """Manages persistent application settings in AppData.
    GitHub PAT is stored securely in the Windows Credential Manager.
    """
    
    _instance = None
    _lock = threading.Lock()
    _config: dict = DEFAULT_CONFIG.copy()

    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ConfigManager, cls).__new__(cls)
                cls._instance._config = DEFAULT_CONFIG.copy()
                cls._instance.load()
        return cls._instance

    def load(self):
        """Load config from disk. Create default if missing."""
        if not os.path.exists(CONFIG_FILE):
            self.save()
            return

        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # Cleanup legacy PAT if it exists in the JSON
                if "github_pat" in loaded:
                    legacy_pat = loaded.pop("github_pat")
                    if legacy_pat and keyring:
                        try:
                            keyring.set_password(
                                "WingetUniversalDashboard", 
                                "github_pat", 
                                legacy_pat
                            )
                            logging.info("Migrated PAT to secure storage.")
                        except Exception as e:
                            logging.error(f"Migration failed: {e}")
                
                # Update but preserve defaults for missing keys
                for key, value in DEFAULT_CONFIG.items():
                    if key not in loaded:
                        loaded[key] = value
                self._config = loaded
        except Exception as e:
            logging.error(f"Failed to load config, using defaults: {e}")

    def save(self):
        """Save current config to disk (thread-safe)."""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save config: {e}")

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._config[key] = value
            self.save()

    @property
    def github_pat(self):
        """Securely fetch PAT from Credential Manager."""
        if keyring:
            try:
                pat = keyring.get_password(
                    "WingetUniversalDashboard", "github_pat"
                )
                return pat or ""
            except Exception as e:
                logging.error(f"Keyring access error: {e}")
        return ""

    @github_pat.setter
    def github_pat(self, value):
        """Securely store PAT in Credential Manager."""
        if keyring:
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
            except Exception as e:
                logging.error(f"Keyring save error: {e}")

    @property
    def auto_detective(self):
        return self.get("auto_detective", True)

    @property
    def url_fallbacks(self):
        return self.get("url_fallbacks", DEFAULT_CONFIG["url_fallbacks"])


"""Non-secret diagnostics snapshot used by GUI and CLI support surfaces."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Callable

from src.app_info import get_build_info
from src.logic.config import CONFIG_DIR, ConfigManager


def _winget_version() -> str | None:
    try:
        completed = subprocess.run(
            ["winget", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def collect_diagnostics(
    *,
    config: ConfigManager | None = None,
    winget_version_getter: Callable[[], str | None] = _winget_version,
) -> dict[str, object]:
    config = config or ConfigManager()
    try:
        import PySide6

        pyside_version = getattr(PySide6, "__version__", None)
    except ImportError:
        pyside_version = None

    ignored = config.ignored_updates
    return {
        "application": get_build_info(),
        "runtime": {
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "pyside6": pyside_version,
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "pid": os.getpid(),
        },
        "winget": {
            "version": winget_version_getter(),
        },
        "settings": {
            "config_dir": CONFIG_DIR,
            "auto_detective": config.auto_detective,
            "check_app_updates": config.check_app_updates,
            "confirm_updates": config.confirm_updates,
            "ignored_updates_count": len(ignored),
            "github_pat_configured": bool(config.github_pat),
        },
    }

"""Runtime product/version identity for source and packaged executions."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

from src.logic.semver import is_valid_semver


APP_NAME = "Winget Universal Dashboard"
APP_REPOSITORY = "CyberIncome/winget-app"
APP_REPOSITORY_URL = f"https://github.com/{APP_REPOSITORY}"
APP_RELEASES_URL = f"{APP_REPOSITORY_URL}/releases"
APP_LATEST_RELEASE_API = (
    f"https://api.github.com/repos/{APP_REPOSITORY}/releases/latest"
)
APP_INSTALLER_ASSET = "WingetUniversalDashboard-Setup-x64.exe"

_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")


def _resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def get_app_version() -> str:
    """Return the public semantic version embedded with the application."""
    try:
        value = (_resource_root() / "VERSION").read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        return "0.0.0+unknown"
    return value if is_valid_semver(value) else "0.0.0+unknown"


def _source_git_commit() -> str | None:
    """Best-effort commit identity for a source checkout, never required at runtime."""
    if getattr(sys, "frozen", False):
        return None
    root = Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = completed.stdout.strip()
    return commit.lower() if _COMMIT_RE.fullmatch(commit) else None


def get_build_info() -> dict[str, object]:
    """Return non-secret build provenance for diagnostics and About surfaces."""
    version = get_app_version()
    payload = _read_json(_resource_root() / "BUILD_INFO.json") or {}
    commit = payload.get("commit")
    dirty = payload.get("dirty")

    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        commit = _source_git_commit()
    else:
        commit = commit.lower()

    if type(dirty) is not bool:
        dirty = None

    embedded_version = payload.get("version")
    if isinstance(embedded_version, str) and is_valid_semver(embedded_version):
        version = embedded_version

    return {
        "name": APP_NAME,
        "version": version,
        "commit": commit,
        "dirty": dirty,
        "frozen": bool(getattr(sys, "frozen", False)),
        "repository": APP_REPOSITORY,
        "repository_url": APP_REPOSITORY_URL,
        "releases_url": APP_RELEASES_URL,
    }


def short_build_label() -> str:
    info = get_build_info()
    commit = info.get("commit")
    if not commit:
        return "development"
    suffix = "-dirty" if info.get("dirty") is True else ""
    return f"{str(commit)[:8]}{suffix}"

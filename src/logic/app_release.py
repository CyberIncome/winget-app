"""Safe GitHub release awareness for Winget Universal Dashboard itself."""

from __future__ import annotations

from src.app_info import (
    APP_INSTALLER_ASSET,
    APP_LATEST_RELEASE_API,
    APP_RELEASES_URL,
)
from src.logic.http_safety import is_safe_https_url, safe_get
from src.logic.semver import compare_semver, parse_semver


def _safe_public_url(value, fallback: str | None = None) -> str | None:
    candidate = str(value or "").strip()
    if is_safe_https_url(candidate):
        return candidate
    return fallback if fallback and is_safe_https_url(fallback) else None


def check_latest_release(
    current_version: str,
    pat: str = "",
    *,
    getter=safe_get,
) -> dict[str, object]:
    """Return bounded, validated release information from GitHub."""
    parse_semver(current_version)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "WingetUniversalDashboard",
        "Cache-Control": "no-cache",
    }
    if pat:
        headers["Authorization"] = f"Bearer {pat}"

    response = getter(
        APP_LATEST_RELEASE_API,
        headers=headers,
        timeout=8,
        max_bytes=512 * 1024,
    )
    if response.status_code == 404:
        return {
            "status": "no-release",
            "current_version": current_version,
            "latest_version": None,
            "update_available": False,
            "release_url": APP_RELEASES_URL,
            "installer_url": None,
        }
    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub latest-release request returned HTTP {response.status_code}"
        )

    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("GitHub latest-release response was not an object")

    tag = str(payload.get("tag_name") or "").strip()
    latest_version = tag[1:] if tag.lower().startswith("v") else tag
    parse_semver(latest_version)

    release_url = _safe_public_url(
        payload.get("html_url"), APP_RELEASES_URL
    )
    installer_url = None
    assets = payload.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            if asset.get("name") != APP_INSTALLER_ASSET:
                continue
            installer_url = _safe_public_url(asset.get("browser_download_url"))
            break

    notes = payload.get("body")
    if not isinstance(notes, str):
        notes = ""
    notes = notes[:4000]

    return {
        "status": "ok",
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": compare_semver(latest_version, current_version) > 0,
        "release_url": release_url,
        "installer_url": installer_url,
        "published_at": payload.get("published_at"),
        "notes": notes,
    }


__all__ = ["check_latest_release", "compare_semver", "parse_semver"]

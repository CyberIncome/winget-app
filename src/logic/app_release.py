"""Safe GitHub release awareness for Winget Universal Dashboard itself."""

from __future__ import annotations

from dataclasses import dataclass
import re

from src.app_info import (
    APP_INSTALLER_ASSET,
    APP_LATEST_RELEASE_API,
    APP_RELEASES_URL,
)
from src.logic.http_safety import is_safe_https_url, safe_get


_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True)
class SemVer:
    core: tuple[int, int, int]
    prerelease: tuple[str, ...] | None


def parse_semver(value: str) -> SemVer:
    text = str(value or "").strip()
    match = _SEMVER_RE.fullmatch(text)
    if not match:
        raise ValueError(f"invalid semantic version: {value!r}")
    prerelease_text = match.group(4)
    prerelease = (
        tuple(prerelease_text.split(".")) if prerelease_text is not None else None
    )
    if prerelease is not None:
        for identifier in prerelease:
            if not identifier:
                raise ValueError(f"invalid semantic version: {value!r}")
            if (
                identifier.isdigit()
                and len(identifier) > 1
                and identifier.startswith("0")
            ):
                raise ValueError(
                    f"numeric prerelease identifier has a leading zero: {value!r}"
                )
    return SemVer(
        (int(match.group(1)), int(match.group(2)), int(match.group(3))),
        prerelease,
    )


def compare_semver(left: str, right: str) -> int:
    """Return -1/0/1 using SemVer precedence; build metadata is ignored."""
    a = parse_semver(left)
    b = parse_semver(right)
    if a.core != b.core:
        return -1 if a.core < b.core else 1
    if a.prerelease is None and b.prerelease is None:
        return 0
    if a.prerelease is None:
        return 1
    if b.prerelease is None:
        return -1

    for left_id, right_id in zip(a.prerelease, b.prerelease):
        if left_id == right_id:
            continue
        left_numeric = left_id.isdigit()
        right_numeric = right_id.isdigit()
        if left_numeric and right_numeric:
            return -1 if int(left_id) < int(right_id) else 1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return -1 if left_id < right_id else 1

    if len(a.prerelease) == len(b.prerelease):
        return 0
    return -1 if len(a.prerelease) < len(b.prerelease) else 1


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

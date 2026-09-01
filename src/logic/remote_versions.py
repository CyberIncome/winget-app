"""Hardened remote-version detection for inventory detective checks."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from src.logic.config import ConfigManager
from src.logic.http_safety import is_safe_https_url, safe_get
from src.logic.parser import is_valid_version, is_version_newer


LOGGER = logging.getLogger(__name__)
_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _newer_or_unknown_install(version: str, installed_version) -> bool:
    return installed_version is None or is_version_newer(
        version, installed_version
    )


def _github_repo_parts(url: str) -> tuple[str, str] | None:
    """Return validated owner/repository names for a github.com repository URL."""
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not _GITHUB_NAME_RE.fullmatch(owner):
        return None
    if not _GITHUB_NAME_RE.fullmatch(repo):
        return None
    return owner, repo


def _github_latest_version(
    url: str, installed_version=None
) -> str | None:
    repo_parts = _github_repo_parts(url)
    if repo_parts is None:
        return None
    owner, repo = repo_parts

    api_url = (
        f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    )
    headers = {"Accept": "application/vnd.github.v3+json"}
    pat = ConfigManager().github_pat
    if pat:
        headers["Authorization"] = f"Bearer {pat}"

    try:
        response = safe_get(api_url, headers=headers, timeout=5)
        if response.status_code == 403:
            remaining = response.headers.get(
                "X-RateLimit-Remaining", "?"
            )
            LOGGER.warning(
                "GitHub API rate limited (remaining: %s); "
                "falling back to the public latest-release redirect.",
                remaining,
            )
        elif response.status_code == 200:
            payload = response.json()
            tag = str(payload.get("tag_name") or "")
            version = tag.lstrip("vV")
            if (
                version
                and is_valid_version(version)
                and _newer_or_unknown_install(version, installed_version)
            ):
                return version
            if version and is_valid_version(version):
                return None
    except Exception as exc:
        LOGGER.debug("GitHub API latest-release lookup failed: %s", exc)

    releases_url = (
        f"https://github.com/{owner}/{repo}/releases/latest"
    )
    try:
        response = safe_get(releases_url, timeout=5)
    except Exception as exc:
        LOGGER.debug("GitHub latest-release redirect failed: %s", exc)
        return None

    if response.status_code != 200 or "/tag/" not in response.url:
        return None
    tag = response.url.split("/tag/", 1)[1].split("/", 1)[0]
    version = tag.lstrip("vV")
    if not is_valid_version(version):
        return None
    if _newer_or_unknown_install(version, installed_version):
        return version
    return None


def _generic_latest_version(
    url: str, installed_version=None
) -> str | None:
    try:
        response = safe_get(url, timeout=5)
    except Exception as exc:
        LOGGER.debug("Generic version URL failed: %s", exc)
        return None
    if response.status_code != 200:
        return None

    versions = re.findall(
        r"[vV]?(\d+\.\d+(?:\.\d+){0,2})\b",
        response.text,
    )
    for version in versions:
        if not is_valid_version(version):
            continue
        if _newer_or_unknown_install(version, installed_version):
            return version
    return None


def check_remote_version(url, installed_version=None):
    """Return a newer remote version using the bounded HTTPS transport."""
    if not is_safe_https_url(url):
        LOGGER.warning("Rejecting unsafe remote-version URL: %r", url)
        return None

    if _github_repo_parts(url) is not None:
        return _github_latest_version(url, installed_version)
    return _generic_latest_version(url, installed_version)


def detect_remote_versions_batch(data, url_fallbacks):
    """Return ``(inventory index, newer version)`` detective hits."""
    results = []
    for index, item in enumerate(data):
        url = item.get("URL")
        if not url:
            item_name = str(item.get("Name", "")).lower()
            for key, fallback in url_fallbacks.items():
                if str(key).lower() in item_name:
                    url = fallback
                    break
        if not url or not is_safe_https_url(url):
            continue

        lowered = str(url).lower()
        if _github_repo_parts(url) is None and "release" not in lowered:
            continue

        remote_version = check_remote_version(
            url, item.get("Version")
        )
        if remote_version:
            results.append((index, remote_version))
    return results

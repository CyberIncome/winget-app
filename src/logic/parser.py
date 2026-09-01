"""Compatibility facade for Windows inventory/version helpers.

The historical implementation is preserved byte-for-byte in
``legacy_parser.py`` because it contains the Windows registry, COM, executable
metadata, and version heuristics used by the application. Public parsing and
network entry points are intentionally overridden here so new/alternate callers
cannot accidentally bypass the hardened protocol and HTTPS layers.
"""

from __future__ import annotations

from src.logic.legacy_parser import *  # noqa: F403
from src.logic.http_safety import is_safe_https_url, safe_get


def _is_safe_url(url):
    """Compatibility alias for the hardened credential-free HTTPS validator."""
    return is_safe_https_url(url)


def _safe_get(url, timeout=5, **kwargs):
    """Compatibility alias for the bounded redirect-aware HTTPS transport."""
    return safe_get(url, timeout=timeout, **kwargs)


def parse_winget_upgrade(output, reg_data=None):
    """Parse Winget output through the strict localized protocol parser."""
    from src.logic.upgrade_parser import parse_winget_upgrade_strict

    return parse_winget_upgrade_strict(output, reg_data=reg_data)


def check_remote_version(url, installed_version=None):
    """Run remote-version detection through the hardened implementation."""
    from src.logic.remote_versions import check_remote_version as hardened_check

    return hardened_check(url, installed_version)


def detect_remote_versions_batch(data, url_fallbacks):
    """Run batch remote-version detection through the hardened implementation."""
    from src.logic.remote_versions import (
        detect_remote_versions_batch as hardened_detect_batch,
    )

    return hardened_detect_batch(data, url_fallbacks)


def detective_scan_worker(data, url_fallbacks, result_queue):
    """Preserve the historical worker envelope with hardened detection."""
    try:
        result_queue.put(
            {"results": detect_remote_versions_batch(data, url_fallbacks)}
        )
    except Exception as exc:
        result_queue.put({"error": str(exc)})

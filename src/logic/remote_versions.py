"""Safe facade for the legacy remote-version detector."""

from __future__ import annotations

from src.logic.http_safety import safe_get


def check_remote_version(url, installed_version=None):
    """Run legacy detection with the hardened HTTP transport installed."""
    from src.logic import parser

    original = parser._safe_get
    parser._safe_get = safe_get
    try:
        return parser.check_remote_version(url, installed_version)
    finally:
        parser._safe_get = original


def detect_remote_versions_batch(data, url_fallbacks):
    """Run legacy batch detection with HTTPS redirect validation."""
    from src.logic import parser

    original = parser._safe_get
    parser._safe_get = safe_get
    try:
        return parser.detect_remote_versions_batch(data, url_fallbacks)
    finally:
        parser._safe_get = original

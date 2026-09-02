"""Process-isolated worker targets used by the hardened GUI.

Each target writes exactly one small result envelope to the supplied
``multiprocessing.Queue``. Expensive Windows/COM/network work therefore lives
outside the Qt process and can be terminated deterministically during shutdown.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable


def _run_worker(result_queue, operation: Callable[[], Any]) -> None:
    """Execute one operation and serialize success/failure across the process."""
    try:
        result_queue.put({"ok": True, "value": operation()})
    except BaseException as exc:  # child boundary: serialize any failure
        result_queue.put(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


def inventory_scan_worker(result_queue) -> None:
    """Collect fresh registry and total inventory data in an isolated process."""

    def operation():
        from src.logic.parser import get_registry_data, get_total_inventory

        reg_data = get_registry_data()
        return {
            "registry": reg_data,
            "inventory": get_total_inventory(reg_data=reg_data),
        }

    _run_worker(result_queue, operation)


def winget_parse_worker(output: str, result_queue) -> None:
    """Parse Winget output and registry enrichment outside the GUI process."""

    def operation():
        from src.logic.upgrade_parser import parse_winget_upgrade_strict

        return parse_winget_upgrade_strict(output)

    _run_worker(result_queue, operation)


def detective_worker(
    data: list[dict], url_fallbacks: dict, result_queue
) -> None:
    """Run remote version detection in an isolated process."""

    def operation():
        from src.logic.remote_versions import detect_remote_versions_batch

        return detect_remote_versions_batch(data, url_fallbacks)

    _run_worker(result_queue, operation)


def github_rate_limit_worker(pat: str, result_queue) -> None:
    """Fetch GitHub rate-limit information through the hardened transport."""

    def operation():
        from src.logic.http_safety import safe_get

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Cache-Control": "no-cache",
        }
        if pat:
            headers["Authorization"] = f"Bearer {pat}"
        response = safe_get(
            "https://api.github.com/rate_limit",
            headers=headers,
            timeout=5,
        )
        payload = response.json() if response.status_code == 200 else None
        return {
            "status_code": response.status_code,
            "payload": payload,
        }

    _run_worker(result_queue, operation)


def app_release_worker(
    current_version: str, pat: str, result_queue
) -> None:
    """Check this application's latest published GitHub release."""

    def operation():
        from src.logic.app_release import check_latest_release

        return check_latest_release(current_version, pat)

    _run_worker(result_queue, operation)

"""Process-isolated worker targets used by the hardened GUI.

Each target writes exactly one small result envelope to the supplied
``multiprocessing.Queue``. Expensive Windows/COM/network work therefore lives
outside the Qt process and can be terminated deterministically during shutdown.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable


def _run_worker(result_queue, operation: Callable[[], Any]) -> None:
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


def detective_worker(data: list[dict], url_fallbacks: dict, result_queue) -> None:
    """Run remote version detection in an isolated process."""

    def operation():
        from src.logic.parser import detect_remote_versions_batch

        return detect_remote_versions_batch(data, url_fallbacks)

    _run_worker(result_queue, operation)


def github_rate_limit_worker(pat: str, result_queue) -> None:
    """Fetch GitHub rate-limit information without a GUI-owned network thread."""

    def operation():
        import requests

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Cache-Control": "no-cache",
        }
        if pat:
            headers["Authorization"] = f"Bearer {pat}"
        response = requests.get(
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

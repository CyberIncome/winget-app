"""Process-isolated worker targets used by the hardened GUI.

Each target writes exactly one small result envelope to the supplied
``multiprocessing.Queue``. Expensive Windows/COM/network work therefore lives
outside the Qt process and can be terminated deterministically during shutdown.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import traceback
from typing import Any, Callable
import uuid


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


def app_release_worker(current_version: str, pat: str, result_queue) -> None:
    """Check the dashboard's own latest stable GitHub release."""

    def operation():
        from src.logic.app_release import check_latest_release

        return check_latest_release(current_version, pat)

    _run_worker(result_queue, operation)


def diagnostics_worker(result_queue) -> None:
    """Collect a non-secret support snapshot outside the Qt process."""

    def operation():
        from src.logic.diagnostics import collect_diagnostics

        return collect_diagnostics()

    _run_worker(result_queue, operation)


def package_show_worker(package_ref: dict, result_queue) -> None:
    """Fetch bounded read-only Winget metadata for one exact package reference."""

    def operation():
        from src.logic.command_runner import run_command
        from src.logic.executor import WingetExecutor

        ref = dict(package_ref or {})
        command = WingetExecutor().get_show_cmd(
            ref.get("value"),
            match_by=ref.get("match_by", "id"),
            source=ref.get("source"),
        )
        result = run_command(
            command,
            timeout=90,
            require_process_tree_containment=True,
        )
        if not result.ok:
            raise RuntimeError(f"winget show {result.failure_summary()}")
        return {
            "ref": ref,
            "output": result.stdout[:256 * 1024],
        }

    _run_worker(result_queue, operation)


def winget_export_worker(
    output_path: str,
    include_versions: bool,
    result_queue,
) -> None:
    """Create and atomically publish a validated WinGet restore-list JSON export."""

    def operation():
        from src.logic.command_runner import run_command
        from src.logic.executor import WingetExecutor

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.wud-export-{os.getpid()}-{uuid.uuid4().hex}.tmp"
        )
        try:
            command = WingetExecutor().get_export_cmd(
                temporary,
                include_versions=bool(include_versions),
            )
            result = run_command(
                command,
                timeout=180,
                require_process_tree_containment=True,
            )
            if not result.ok:
                raise RuntimeError(f"winget export {result.failure_summary()}")
            if not temporary.is_file():
                raise RuntimeError(
                    "winget export exited successfully but created no temporary file"
                )
            size = temporary.stat().st_size
            if size <= 0 or size > 16 * 1024 * 1024:
                raise RuntimeError(
                    f"winget export produced an invalid file size: {size} bytes"
                )
            try:
                payload = json.loads(temporary.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("winget export did not produce valid JSON") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("winget export JSON root was not an object")

            os.replace(temporary, destination)
            return {
                "path": str(destination),
                "size": size,
                "include_versions": bool(include_versions),
            }
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    _run_worker(result_queue, operation)

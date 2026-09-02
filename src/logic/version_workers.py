"""Managed workers for version provenance and exact package inspection."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from src.logic.worker_jobs import _run_worker


def winget_version_map_worker(result_queue) -> None:
    """Export source package versions without blocking the Qt process."""

    def operation():
        from src.logic.command_runner import run_command
        from src.logic.executor import WingetExecutor
        from src.logic.version_provenance import extract_export_version_records

        with tempfile.TemporaryDirectory(prefix="wud-version-map-") as temp_dir:
            destination = Path(temp_dir) / "installed-packages.json"
            command = WingetExecutor().get_export_cmd(
                destination,
                include_versions=True,
            )
            result = run_command(command, timeout=180)
            if not result.ok:
                raise RuntimeError(
                    f"winget export --include-versions {result.failure_summary()}"
                )
            if not destination.is_file():
                raise RuntimeError(
                    "winget export --include-versions created no JSON file"
                )
            size = destination.stat().st_size
            if size <= 0 or size > 16 * 1024 * 1024:
                raise RuntimeError(
                    f"winget version-map export size was invalid: {size} bytes"
                )
            try:
                payload = json.loads(
                    destination.read_text(encoding="utf-8-sig")
                )
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    "winget version-map export did not contain valid JSON"
                ) from exc
            records = extract_export_version_records(payload)
            return {
                "records": records,
                "matched_packages": len(records),
            }

    _run_worker(result_queue, operation)


def exact_package_show_worker(package_ref: dict, result_queue) -> None:
    """Load bounded metadata for the exact source target displayed by the scan."""

    def operation():
        from src.logic.command_runner import run_command
        from src.logic.executor import WingetExecutor

        ref = dict(package_ref or {})
        command = WingetExecutor().get_show_cmd(
            ref.get("value"),
            match_by=ref.get("match_by", "id"),
            source=ref.get("source"),
            version=ref.get("version"),
        )
        result = run_command(command, timeout=90)
        if not result.ok:
            raise RuntimeError(f"winget show {result.failure_summary()}")
        return {
            "ref": ref,
            "output": result.stdout[:256 * 1024],
        }

    _run_worker(result_queue, operation)

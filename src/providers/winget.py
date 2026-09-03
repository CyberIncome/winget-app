"""WinGet adapter for the additive provider architecture.

The existing GUI remains the accepted WinGet execution path during migration.
This adapter reuses the same strict scan/provenance logic and can produce exact
provider actions, but the provider CLI exposes scans only.
"""

from __future__ import annotations

import shutil
from typing import Callable

from src.logic.command_runner import CommandResult, run_command
from src.logic.executor import WingetExecutor
from src.logic.parser import get_registry_data
from src.logic.upgrade_parser import WingetParseError, parse_winget_upgrade_strict
from src.logic.version_provenance import annotate_version_row
from src.providers.base import (
    ActionKind,
    ProviderAction,
    ProviderCapability,
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderStatus,
    ProviderUpdate,
)


def _result_ok(result: CommandResult) -> bool:
    return (
        not result.timed_out
        and result.start_error is None
        and not result.output_overflow
        and result.containment_error is None
        and result.returncode == 0
    )


def winget_rows_to_provider_updates(rows: list[dict]) -> tuple[ProviderUpdate, ...]:
    """Normalize strict WinGet rows without discarding version provenance."""
    updates = []
    for source_row in rows:
        row = annotate_version_row(dict(source_row))
        package_id = str(row.get("Id") or "").strip()
        name = str(row.get("Name") or package_id).strip()
        installed = str(row.get("Version") or "").strip() or None
        available = str(row.get("Available") or "").strip() or None
        source = str(row.get("Source") or "winget").strip()
        if not package_id or not available:
            continue
        updates.append(
            ProviderUpdate(
                provider_id="winget",
                item_id=package_id,
                name=name,
                installed_version=installed,
                available_version=available,
                category=(
                    ProviderCategory.STORE
                    if source.casefold() == "msstore"
                    else ProviderCategory.APPLICATION
                ),
                mode=ProviderMode.MANAGED,
                can_update=True,
                source=source,
                metadata={
                    "version_status": row.get("VersionStatus"),
                    "version_needs_review": bool(row.get("VersionNeedsReview")),
                    "version_explanation": row.get("VersionExplanation"),
                },
            )
        )
    return tuple(updates)


class WingetProvider:
    """Read-only WinGet scan adapter plus exact update-plan construction."""

    provider_id = "winget"

    def __init__(
        self,
        *,
        runner: Callable = run_command,
        registry_loader: Callable = get_registry_data,
        executable: str | None = None,
    ):
        self._runner = runner
        self._registry_loader = registry_loader
        self._configured_executable = executable

    def _executable(self) -> str | None:
        return self._configured_executable or shutil.which("winget")

    def probe(self) -> ProviderStatus:
        executable = self._executable()
        if not executable:
            return ProviderStatus(
                provider_id=self.provider_id,
                display_name="WinGet",
                mode=ProviderMode.MANAGED,
                category=ProviderCategory.APPLICATION,
                available=False,
                reason="winget executable was not found on PATH",
            )
        version = None
        result = self._runner([executable, "--version"], timeout=15)
        if _result_ok(result):
            version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name="WinGet",
            mode=ProviderMode.MANAGED,
            category=ProviderCategory.APPLICATION,
            available=True,
            capabilities=(
                ProviderCapability.DETECT,
                ProviderCapability.UPDATE,
                ProviderCapability.BULK_UPDATE,
                ProviderCapability.EXACT_TARGET,
                ProviderCapability.PROGRESS,
            ),
            executable=executable,
            version=version,
        )

    def scan_updates(self) -> ProviderScanResult:
        status = self.probe()
        if not status.available or not status.executable:
            return ProviderScanResult(status=status)
        command = WingetExecutor().get_check_updates_cmd()
        command[0] = status.executable
        result = self._runner(command, timeout=300)
        if not _result_ok(result):
            return ProviderScanResult(
                status=status,
                error=f"WinGet scan {result.failure_summary()}",
            )
        try:
            parsed = parse_winget_upgrade_strict(
                result.stdout,
                reg_data=self._registry_loader(),
            )
        except WingetParseError as exc:
            return ProviderScanResult(
                status=status,
                error=f"WinGet output could not be parsed safely: {exc}",
            )
        return ProviderScanResult(
            status=status,
            updates=winget_rows_to_provider_updates(parsed),
        )

    def plan_update(self, update: ProviderUpdate) -> ProviderAction:
        if update.provider_id != self.provider_id:
            raise ValueError("WinGet provider cannot execute another provider's update")
        if not update.available_version:
            return ProviderAction(
                provider_id=self.provider_id,
                item_id=update.item_id,
                kind=ActionKind.NONE,
                description="WinGet update has no exact target version",
            )
        executable = self._executable()
        if not executable:
            return ProviderAction(
                provider_id=self.provider_id,
                item_id=update.item_id,
                kind=ActionKind.NONE,
                description="WinGet is no longer available",
            )
        source = str(update.source or "").strip() or None
        command = WingetExecutor().get_update_cmd(
            update.item_id,
            source=source,
            version=update.available_version,
        )
        command[0] = executable
        return ProviderAction(
            provider_id=self.provider_id,
            item_id=update.item_id,
            kind=ActionKind.COMMAND,
            target_version=update.available_version,
            command=tuple(command),
            requires_elevation=False,
            description="Execute exact WinGet package target",
        )

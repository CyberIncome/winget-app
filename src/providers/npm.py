"""npm global-package provider using JSON outdated output."""

from __future__ import annotations

import json
import shutil
from typing import Callable

from src.logic.command_runner import CommandResult, run_command
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


def parse_npm_outdated(text: str) -> tuple[ProviderUpdate, ...]:
    """Parse ``npm outdated --global --json --depth=0`` output."""
    try:
        payload = json.loads(str(text or "{}"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid npm outdated JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("npm outdated JSON must be an object")

    updates = []
    for package_name in sorted(payload, key=str.casefold):
        record = payload.get(package_name)
        if not isinstance(record, dict):
            continue
        current = str(record.get("current") or "").strip()
        available = str(record.get("latest") or record.get("wanted") or "").strip()
        if not current or not available or current == available:
            continue
        updates.append(
            ProviderUpdate(
                provider_id="npm-global",
                item_id=package_name,
                name=package_name,
                installed_version=current,
                available_version=available,
                category=ProviderCategory.DEVELOPMENT,
                mode=ProviderMode.MANAGED,
                can_update=True,
                source="npm-global",
                metadata={
                    "wanted": record.get("wanted"),
                    "latest": record.get("latest"),
                    "location": record.get("location"),
                },
            )
        )
    return tuple(updates)


def _structurally_ok(result: CommandResult) -> bool:
    return (
        not result.timed_out
        and result.start_error is None
        and not result.output_overflow
        and result.containment_error is None
    )


class NpmGlobalProvider:
    """Detect and plan exact updates for globally installed npm packages."""

    provider_id = "npm-global"

    def __init__(
        self,
        *,
        runner: Callable = run_command,
        executable: str | None = None,
    ):
        self._runner = runner
        self._configured_executable = executable

    def _executable(self) -> str | None:
        return self._configured_executable or shutil.which("npm")

    def probe(self) -> ProviderStatus:
        executable = self._executable()
        if not executable:
            return ProviderStatus(
                provider_id=self.provider_id,
                display_name="npm globals",
                mode=ProviderMode.MANAGED,
                category=ProviderCategory.DEVELOPMENT,
                available=False,
                reason="npm executable was not found on PATH",
            )
        version = None
        result = self._runner([executable, "--version"], timeout=15)
        if _structurally_ok(result) and result.returncode == 0:
            version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name="npm globals",
            mode=ProviderMode.MANAGED,
            category=ProviderCategory.DEVELOPMENT,
            available=True,
            capabilities=(
                ProviderCapability.DETECT,
                ProviderCapability.UPDATE,
                ProviderCapability.BULK_UPDATE,
                ProviderCapability.EXACT_TARGET,
            ),
            executable=executable,
            version=version,
        )

    def scan_updates(self) -> ProviderScanResult:
        status = self.probe()
        if not status.available or not status.executable:
            return ProviderScanResult(status=status)
        result = self._runner(
            [
                status.executable,
                "outdated",
                "--global",
                "--json",
                "--depth=0",
            ],
            timeout=180,
        )
        if not _structurally_ok(result) or result.returncode not in (0, 1):
            return ProviderScanResult(
                status=status,
                error=f"npm scan {result.failure_summary()}",
            )
        try:
            updates = parse_npm_outdated(result.stdout)
        except ValueError as exc:
            return ProviderScanResult(status=status, error=str(exc))
        warnings = ()
        if result.returncode == 1:
            warnings = (
                "npm returned status 1 with valid outdated JSON; some npm "
                "versions use this status when updates are present",
            )
        return ProviderScanResult(
            status=status,
            updates=updates,
            warnings=warnings,
        )

    def plan_update(self, update: ProviderUpdate) -> ProviderAction:
        if update.provider_id != self.provider_id:
            raise ValueError("npm provider cannot execute another provider's update")
        executable = self._executable()
        if not executable:
            return ProviderAction(
                provider_id=self.provider_id,
                item_id=update.item_id,
                kind=ActionKind.NONE,
                description="npm is no longer available",
            )
        package_spec = f"{update.item_id}@{update.available_version}"
        return ProviderAction(
            provider_id=self.provider_id,
            item_id=update.item_id,
            kind=ActionKind.COMMAND,
            target_version=update.available_version,
            command=(
                executable,
                "install",
                "--global",
                package_spec,
            ),
            requires_elevation=False,
            description="Install exact global npm package target",
        )

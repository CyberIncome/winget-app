"""Chocolatey provider using documented machine-readable CLI output."""

from __future__ import annotations

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


def parse_chocolatey_outdated(text: str) -> tuple[ProviderUpdate, ...]:
    """Parse ``choco outdated --limit-output`` records.

    Chocolatey's limited output uses four pipe-delimited fields:
    package id, installed version, available version, and pinned state.
    Malformed lines are ignored rather than guessed into package identities.
    """
    updates = []
    seen = set()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("chocolatey v"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            continue
        package_id, installed, available, pinned_text = parts
        if not package_id or not installed or not available:
            continue
        identity = package_id.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        pinned = pinned_text.casefold() == "true"
        updates.append(
            ProviderUpdate(
                provider_id="chocolatey",
                item_id=package_id,
                name=package_id,
                installed_version=installed,
                available_version=available,
                category=ProviderCategory.APPLICATION,
                mode=ProviderMode.MANAGED,
                can_update=not pinned,
                source="chocolatey",
                blocked_reason=(
                    "Package is pinned in Chocolatey" if pinned else None
                ),
                metadata={"pinned": pinned},
            )
        )
    return tuple(updates)


def _command_completed(
    result: CommandResult,
    *,
    allowed_codes: tuple[int, ...] = (0,),
) -> bool:
    return (
        not result.timed_out
        and result.start_error is None
        and not result.output_overflow
        and result.containment_error is None
        and result.returncode in allowed_codes
    )


class ChocolateyProvider:
    """Detect and plan exact-version upgrades for Chocolatey packages."""

    provider_id = "chocolatey"

    def __init__(
        self,
        *,
        runner: Callable = run_command,
        executable: str | None = None,
    ):
        self._runner = runner
        self._configured_executable = executable

    def _executable(self) -> str | None:
        if self._configured_executable:
            return self._configured_executable
        return shutil.which("choco")

    def probe(self) -> ProviderStatus:
        executable = self._executable()
        if not executable:
            return ProviderStatus(
                provider_id=self.provider_id,
                display_name="Chocolatey",
                mode=ProviderMode.MANAGED,
                category=ProviderCategory.APPLICATION,
                available=False,
                reason="choco executable was not found on PATH",
            )

        version = None
        result = self._runner([executable, "--version"], timeout=15)
        if _command_completed(result):
            version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name="Chocolatey",
            mode=ProviderMode.MANAGED,
            category=ProviderCategory.APPLICATION,
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
            [status.executable, "outdated", "--limit-output", "--no-color"],
            timeout=180,
        )
        # Chocolatey enhanced exit codes use 2 to mean outdated packages found.
        if not _command_completed(result, allowed_codes=(0, 2)):
            return ProviderScanResult(
                status=status,
                error=f"Chocolatey scan {result.failure_summary()}",
            )
        return ProviderScanResult(
            status=status,
            updates=parse_chocolatey_outdated(result.stdout),
        )

    def plan_update(self, update: ProviderUpdate) -> ProviderAction:
        if update.provider_id != self.provider_id:
            raise ValueError(
                "Chocolatey provider cannot execute another provider's update"
            )
        if not update.can_update:
            return ProviderAction(
                provider_id=self.provider_id,
                item_id=update.item_id,
                kind=ActionKind.NONE,
                description=update.blocked_reason or "Chocolatey update is blocked",
            )
        executable = self._executable()
        if not executable:
            return ProviderAction(
                provider_id=self.provider_id,
                item_id=update.item_id,
                kind=ActionKind.NONE,
                description="Chocolatey is no longer available",
            )
        return ProviderAction(
            provider_id=self.provider_id,
            item_id=update.item_id,
            kind=ActionKind.COMMAND,
            target_version=update.available_version,
            command=(
                executable,
                "upgrade",
                update.item_id,
                "--version",
                str(update.available_version),
                "--yes",
                "--no-progress",
            ),
            requires_elevation=True,
            description="Upgrade exact Chocolatey package target",
        )

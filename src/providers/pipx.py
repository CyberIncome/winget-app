"""pipx provider using its structured outdated JSON protocol."""

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


def parse_pipx_outdated(text: str) -> tuple[ProviderUpdate, ...]:
    """Parse ``pipx list --outdated --output=json`` output."""
    try:
        payload = json.loads(str(text or ""))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid pipx JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("pipx outdated output must be a JSON object")
    if payload.get("status") not in {None, "success", "partial"}:
        raise ValueError(f"pipx reported status {payload.get('status')!r}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("pipx outdated output is missing data")
    packages = data.get("packages")
    if not isinstance(packages, list):
        raise ValueError("pipx outdated output is missing package records")

    updates = []
    seen = set()
    for record in packages:
        if not isinstance(record, dict):
            continue
        environment = str(record.get("environment") or "").strip()
        package = str(record.get("package") or environment).strip()
        installed = str(record.get("version") or "").strip()
        available = str(record.get("latest_version") or "").strip()
        if not environment or not package or not installed or not available:
            continue
        identity = environment.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        pinned = bool(record.get("pinned"))
        updates.append(
            ProviderUpdate(
                provider_id="pipx",
                item_id=environment,
                name=package,
                installed_version=installed,
                available_version=available,
                category=ProviderCategory.DEVELOPMENT,
                mode=ProviderMode.MANAGED,
                can_update=not pinned,
                source="pipx",
                blocked_reason="pipx environment is pinned" if pinned else None,
                metadata={
                    "environment": environment,
                    "package": package,
                    "injected": bool(record.get("injected")),
                    "pinned": pinned,
                },
            )
        )
    return tuple(updates)


def _result_ok(result: CommandResult) -> bool:
    return (
        not result.timed_out
        and result.start_error is None
        and not result.output_overflow
        and result.containment_error is None
        and result.returncode == 0
    )


class PipxProvider:
    """Detect and plan exact target upgrades for pipx environments."""

    provider_id = "pipx"

    def __init__(
        self,
        *,
        runner: Callable = run_command,
        executable: str | None = None,
    ):
        self._runner = runner
        self._configured_executable = executable

    def _executable(self) -> str | None:
        return self._configured_executable or shutil.which("pipx")

    def probe(self) -> ProviderStatus:
        executable = self._executable()
        if not executable:
            return ProviderStatus(
                provider_id=self.provider_id,
                display_name="pipx",
                mode=ProviderMode.MANAGED,
                category=ProviderCategory.DEVELOPMENT,
                available=False,
                reason="pipx executable was not found on PATH",
            )
        version = None
        result = self._runner([executable, "--version"], timeout=15)
        if _result_ok(result):
            version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name="pipx",
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
                "list",
                "--outdated",
                "--output=json",
            ],
            timeout=180,
        )
        if not _result_ok(result):
            return ProviderScanResult(
                status=status,
                error=f"pipx scan {result.failure_summary()}",
            )
        try:
            updates = parse_pipx_outdated(result.stdout)
        except ValueError as exc:
            return ProviderScanResult(status=status, error=str(exc))
        return ProviderScanResult(status=status, updates=updates)

    def plan_update(self, update: ProviderUpdate) -> ProviderAction:
        if update.provider_id != self.provider_id:
            raise ValueError("pipx provider cannot execute another provider's update")
        if not update.can_update:
            return ProviderAction(
                provider_id=self.provider_id,
                item_id=update.item_id,
                kind=ActionKind.NONE,
                description=update.blocked_reason or "pipx update is blocked",
            )
        executable = self._executable()
        if not executable:
            return ProviderAction(
                provider_id=self.provider_id,
                item_id=update.item_id,
                kind=ActionKind.NONE,
                description="pipx is no longer available",
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
                "--install",
                "--pip-args",
                f"{update.name}=={update.available_version}",
            ),
            requires_elevation=False,
            description="Upgrade exact pipx environment target",
        )

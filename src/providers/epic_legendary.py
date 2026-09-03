"""Optional Epic Games update detection through Legendary.

Legendary exposes a stable CSV listing for installed games plus remote build
versions. Detection is useful today, but this provider intentionally remains
informational until WUD can bind execution to the exact Legendary manifest/build
seen by the scan. A generic ``legendary install --update-only`` resolves latest
again at execution time and therefore does not satisfy the provider exact-target
contract.
"""

from __future__ import annotations

import csv
import io
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

_EXPECTED_COLUMNS = (
    "App name",
    "App title",
    "Installed version",
    "Available version",
    "Update available",
    "Install size",
    "Install path",
    "Platform",
)


def _parse_bool(value: str) -> bool | None:
    normalized = str(value or "").strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def parse_legendary_installed_updates(text: str) -> tuple[ProviderUpdate, ...]:
    """Parse Legendary's installed-games CSV and return update rows only."""
    stream = io.StringIO(str(text or ""))
    reader = csv.DictReader(stream)
    if tuple(reader.fieldnames or ()) != _EXPECTED_COLUMNS:
        raise ValueError(
            "Legendary CSV schema changed or is incomplete: "
            f"{reader.fieldnames!r}"
        )

    updates = []
    seen = set()
    for row in reader:
        app_name = str(row.get("App name") or "").strip()
        title = str(row.get("App title") or app_name).strip()
        installed = str(row.get("Installed version") or "").strip()
        available = str(row.get("Available version") or "").strip()
        update_available = _parse_bool(row.get("Update available"))
        if update_available is not True:
            continue
        if not app_name or not title or not installed or not available:
            continue
        key = app_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        updates.append(
            ProviderUpdate(
                provider_id="epic-legendary",
                item_id=app_name,
                name=title,
                installed_version=installed,
                available_version=available,
                category=ProviderCategory.GAME,
                mode=ProviderMode.INFORMATIONAL,
                can_update=False,
                source="epic-legendary",
                blocked_reason=(
                    "Legendary can update this game, but exact scanned-build "
                    "execution is not bound yet"
                ),
                metadata={
                    "install_size": row.get("Install size"),
                    "install_path": row.get("Install path"),
                    "platform": row.get("Platform"),
                    "third_party_client": "Legendary",
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


class EpicLegendaryProvider:
    """Detect Epic game updates when the user already has Legendary installed."""

    provider_id = "epic-legendary"

    def __init__(
        self,
        *,
        runner: Callable = run_command,
        executable: str | None = None,
    ):
        self._runner = runner
        self._configured_executable = executable

    def _executable(self) -> str | None:
        return self._configured_executable or shutil.which("legendary")

    def probe(self) -> ProviderStatus:
        executable = self._executable()
        if not executable:
            return ProviderStatus(
                provider_id=self.provider_id,
                display_name="Epic Games (Legendary)",
                mode=ProviderMode.INFORMATIONAL,
                category=ProviderCategory.GAME,
                available=False,
                reason=(
                    "Legendary is not installed; Epic integration is optional "
                    "and is never bundled or authenticated automatically"
                ),
                requires_opt_in=True,
            )
        version = None
        result = self._runner([executable, "--version"], timeout=15)
        if _result_ok(result):
            version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name="Epic Games (Legendary)",
            mode=ProviderMode.INFORMATIONAL,
            category=ProviderCategory.GAME,
            available=True,
            capabilities=(ProviderCapability.DETECT,),
            executable=executable,
            version=version,
            requires_opt_in=True,
        )

    def scan_updates(self) -> ProviderScanResult:
        status = self.probe()
        if not status.available or not status.executable:
            return ProviderScanResult(status=status)
        result = self._runner(
            [
                status.executable,
                "list-installed",
                "--check-updates",
                "--csv",
            ],
            timeout=300,
        )
        if not _result_ok(result):
            return ProviderScanResult(
                status=status,
                error=(
                    "Legendary Epic scan failed; authentication may be required: "
                    f"{result.failure_summary()}"
                ),
            )
        try:
            updates = parse_legendary_installed_updates(result.stdout)
        except ValueError as exc:
            return ProviderScanResult(status=status, error=str(exc))
        return ProviderScanResult(status=status, updates=updates)

    def plan_update(self, update: ProviderUpdate) -> ProviderAction:
        if update.provider_id != self.provider_id:
            raise ValueError(
                "Epic Legendary provider cannot execute another provider's update"
            )
        return ProviderAction(
            provider_id=self.provider_id,
            item_id=update.item_id,
            kind=ActionKind.NONE,
            target_version=None,
            description=(
                "Exact Legendary build execution is not enabled; use the "
                "owning Epic/Legendary client until manifest-bound execution "
                "is implemented"
            ),
        )

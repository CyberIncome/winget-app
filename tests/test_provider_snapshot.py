from __future__ import annotations

from src.providers.base import (
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderStatus,
    ProviderUpdate,
)
from src.providers.snapshot import ProviderSnapshot


def _status(provider_id, *, available=True):
    return ProviderStatus(
        provider_id=provider_id,
        display_name=provider_id.title(),
        mode=ProviderMode.MANAGED,
        category=ProviderCategory.APPLICATION,
        available=available,
        reason=None if available else "not installed",
    )


def _update(
    provider_id,
    item_id,
    *,
    category=ProviderCategory.APPLICATION,
    mode=ProviderMode.MANAGED,
    can_update=True,
):
    return ProviderUpdate(
        provider_id=provider_id,
        item_id=item_id,
        name=item_id,
        installed_version="1",
        available_version="2",
        category=category,
        mode=mode,
        can_update=can_update,
        blocked_reason=("blocked" if not can_update else None),
    )


def test_snapshot_keeps_managed_handoff_and_blocked_counts_separate():
    snapshot = ProviderSnapshot(
        (
            ProviderScanResult(
                status=_status("winget"),
                updates=(
                    _update("winget", "app"),
                    _update(
                        "winget",
                        "pinned",
                        can_update=False,
                    ),
                ),
            ),
            ProviderScanResult(
                status=ProviderStatus(
                    provider_id="steam",
                    display_name="Steam",
                    mode=ProviderMode.HANDOFF,
                    category=ProviderCategory.GAME,
                    available=True,
                ),
                updates=(
                    _update(
                        "steam",
                        "game",
                        category=ProviderCategory.GAME,
                        mode=ProviderMode.HANDOFF,
                        can_update=False,
                    ),
                ),
            ),
        )
    )
    assert snapshot.total_updates == 3
    assert snapshot.managed_updates == 1
    assert snapshot.blocked_updates == 1
    assert snapshot.handoff_updates == 1
    assert snapshot.counts_by_provider() == {"winget": 2, "steam": 1}
    assert snapshot.counts_by_category()["application"] == 2
    assert snapshot.counts_by_category()["game"] == 1


def test_failed_provider_is_not_treated_as_zero_update_success():
    snapshot = ProviderSnapshot(
        (
            ProviderScanResult(
                status=_status("winget"),
                updates=(_update("winget", "app"),),
            ),
            ProviderScanResult(
                status=_status("steam"),
                error="network timeout",
            ),
        )
    )
    assert snapshot.total_updates == 1
    assert snapshot.provider_failures == 1
    assert snapshot.failed_provider_ids() == ("steam",)
    data = snapshot.to_dict()
    assert data["counts_by_provider"]["steam"] == 0
    assert data["provider_failures"] == 1
    assert data["results"][1]["error"] == "network timeout"


def test_unavailable_provider_is_distinct_from_failed_provider():
    snapshot = ProviderSnapshot(
        (ProviderScanResult(status=_status("pipx", available=False)),)
    )
    assert snapshot.total_updates == 0
    assert snapshot.provider_failures == 0
    assert snapshot.failed_provider_ids() == ()

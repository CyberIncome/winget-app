from __future__ import annotations

from src.providers.base import (
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderStatus,
    ProviderUpdate,
)
from src.providers.snapshot import ProviderSnapshot


def _update(provider_id, item_id, mode, can_update):
    return ProviderUpdate(
        provider_id=provider_id,
        item_id=item_id,
        name=item_id,
        installed_version="1",
        available_version="2",
        category=ProviderCategory.GAME,
        mode=mode,
        can_update=can_update,
        blocked_reason="provider-owned" if not can_update else None,
    )


def test_snapshot_exposes_informational_count_separately():
    status = ProviderStatus(
        provider_id="epic",
        display_name="Epic",
        mode=ProviderMode.INFORMATIONAL,
        category=ProviderCategory.GAME,
        available=True,
    )
    snapshot = ProviderSnapshot(
        (
            ProviderScanResult(
                status=status,
                updates=(
                    _update(
                        "epic",
                        "game",
                        ProviderMode.INFORMATIONAL,
                        False,
                    ),
                ),
            ),
        )
    )
    assert snapshot.total_updates == 1
    assert snapshot.managed_updates == 0
    assert snapshot.handoff_updates == 0
    assert snapshot.informational_updates == 1
    assert snapshot.blocked_updates == 0
    assert snapshot.to_dict()["informational_updates"] == 1

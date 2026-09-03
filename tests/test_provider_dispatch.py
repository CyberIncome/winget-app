from __future__ import annotations

import pytest

from src.providers.base import (
    ActionKind,
    ProviderAction,
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderStatus,
    ProviderUpdate,
)
from src.providers.registry import ProviderRegistry


def _update(
    *,
    provider_id="alpha",
    item_id="pkg",
    available="2.0",
    can_update=True,
    mode=ProviderMode.MANAGED,
):
    return ProviderUpdate(
        provider_id=provider_id,
        item_id=item_id,
        name="Package",
        installed_version="1.0",
        available_version=available,
        category=ProviderCategory.APPLICATION,
        mode=mode,
        can_update=can_update,
    )


class _Provider:
    provider_id = "alpha"

    def __init__(self, planner):
        self._planner = planner

    def probe(self):
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name="Alpha",
            mode=ProviderMode.MANAGED,
            category=ProviderCategory.APPLICATION,
            available=True,
        )

    def scan_updates(self):
        return ProviderScanResult(status=self.probe())

    def plan_update(self, update):
        return self._planner(update)


def test_registry_routes_update_only_to_named_owner():
    calls = []

    def planner(update):
        calls.append(update.provider_id)
        return ProviderAction(
            provider_id="alpha",
            item_id=update.item_id,
            kind=ActionKind.COMMAND,
            target_version=update.available_version,
            command=("alpha", "upgrade", update.item_id, update.available_version),
        )

    action = ProviderRegistry([_Provider(planner)]).plan_update(_update())
    assert calls == ["alpha"]
    assert action.command[-1] == "2.0"


def test_registry_rejects_action_that_changes_provider_owner():
    provider = _Provider(
        lambda update: ProviderAction(
            provider_id="beta",
            item_id=update.item_id,
            kind=ActionKind.COMMAND,
            target_version=update.available_version,
            command=("tool",),
        )
    )
    with pytest.raises(ValueError, match="provider ownership"):
        ProviderRegistry([provider]).plan_update(_update())


def test_registry_rejects_action_that_changes_item_identity():
    provider = _Provider(
        lambda update: ProviderAction(
            provider_id="alpha",
            item_id="other",
            kind=ActionKind.COMMAND,
            target_version=update.available_version,
            command=("tool",),
        )
    )
    with pytest.raises(ValueError, match="item identity"):
        ProviderRegistry([provider]).plan_update(_update())


def test_registry_rejects_action_that_changes_scanned_target():
    provider = _Provider(
        lambda update: ProviderAction(
            provider_id="alpha",
            item_id=update.item_id,
            kind=ActionKind.COMMAND,
            target_version="3.0",
            command=("tool",),
        )
    )
    with pytest.raises(ValueError, match="scanned target"):
        ProviderRegistry([provider]).plan_update(_update())


def test_registry_rejects_command_for_blocked_update():
    provider = _Provider(
        lambda update: ProviderAction(
            provider_id="alpha",
            item_id=update.item_id,
            kind=ActionKind.COMMAND,
            target_version=update.available_version,
            command=("tool",),
        )
    )
    with pytest.raises(ValueError, match="blocked update"):
        ProviderRegistry([provider]).plan_update(_update(can_update=False))


def test_registry_allows_explicit_none_if_provider_disappeared():
    provider = _Provider(
        lambda update: ProviderAction(
            provider_id="alpha",
            item_id=update.item_id,
            kind=ActionKind.NONE,
            description="provider executable is no longer available",
        )
    )
    action = ProviderRegistry([provider]).plan_update(_update())
    assert action.kind == ActionKind.NONE


def test_registry_accepts_handoff_only_for_handoff_update():
    provider = _Provider(
        lambda update: ProviderAction(
            provider_id="alpha",
            item_id=update.item_id,
            kind=ActionKind.HANDOFF,
            uri="alpha://updates",
        )
    )
    update = _update(can_update=False, mode=ProviderMode.HANDOFF)
    assert ProviderRegistry([provider]).plan_update(update).kind == ActionKind.HANDOFF

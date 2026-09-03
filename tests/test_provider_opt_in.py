from __future__ import annotations

from src.providers.base import (
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderStatus,
)
from src.providers.registry import ProviderRegistry


class _OptInProvider:
    provider_id = "account-provider"

    def __init__(self):
        self.scan_calls = 0

    def probe(self):
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name="Account Provider",
            mode=ProviderMode.INFORMATIONAL,
            category=ProviderCategory.GAME,
            available=True,
            requires_opt_in=True,
        )

    def scan_updates(self):
        self.scan_calls += 1
        return ProviderScanResult(status=self.probe())

    def plan_update(self, update):
        raise NotImplementedError


def test_default_scan_does_not_touch_opt_in_provider_account_surface():
    provider = _OptInProvider()
    result = ProviderRegistry([provider]).scan_all()[0]
    assert provider.scan_calls == 0
    assert result.ok is True
    assert result.updates == ()
    assert result.warnings == (
        "provider requires explicit opt-in and was not scanned",
    )


def test_explicit_provider_selection_is_opt_in_signal_for_read_only_scan():
    provider = _OptInProvider()
    result = ProviderRegistry([provider]).scan_all([provider.provider_id])[0]
    assert provider.scan_calls == 1
    assert result.ok is True
    assert result.warnings == ()


def test_status_json_exposes_opt_in_requirement():
    status = _OptInProvider().probe().to_dict()
    assert status["requires_opt_in"] is True

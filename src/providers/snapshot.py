"""Immutable aggregation helpers for universal update snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from src.providers.base import (
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderUpdate,
)


@dataclass(frozen=True)
class ProviderSnapshot:
    """One point-in-time aggregate without hiding provider failures."""

    results: tuple[ProviderScanResult, ...]

    @property
    def updates(self) -> tuple[ProviderUpdate, ...]:
        return tuple(
            update
            for result in self.results
            if result.ok
            for update in result.updates
        )

    @property
    def total_updates(self) -> int:
        return len(self.updates)

    @property
    def managed_updates(self) -> int:
        return sum(
            1
            for update in self.updates
            if update.mode == ProviderMode.MANAGED and update.can_update
        )

    @property
    def handoff_updates(self) -> int:
        return sum(
            1 for update in self.updates if update.mode == ProviderMode.HANDOFF
        )

    @property
    def blocked_updates(self) -> int:
        return sum(
            1
            for update in self.updates
            if update.mode == ProviderMode.MANAGED and not update.can_update
        )

    @property
    def provider_failures(self) -> int:
        return sum(1 for result in self.results if not result.ok)

    @property
    def warning_count(self) -> int:
        return sum(len(result.warnings) for result in self.results)

    def counts_by_provider(self) -> dict[str, int]:
        return {
            result.status.provider_id: len(result.updates) if result.ok else 0
            for result in self.results
        }

    def counts_by_category(self) -> dict[str, int]:
        counts = {category.value: 0 for category in ProviderCategory}
        for update in self.updates:
            counts[update.category.value] += 1
        return counts

    def failed_provider_ids(self) -> tuple[str, ...]:
        return tuple(
            result.status.provider_id for result in self.results if not result.ok
        )

    def to_dict(self) -> dict:
        return {
            "total_updates": self.total_updates,
            "managed_updates": self.managed_updates,
            "handoff_updates": self.handoff_updates,
            "blocked_updates": self.blocked_updates,
            "provider_failures": self.provider_failures,
            "warning_count": self.warning_count,
            "counts_by_provider": self.counts_by_provider(),
            "counts_by_category": self.counts_by_category(),
            "failed_provider_ids": list(self.failed_provider_ids()),
            "results": [result.to_dict() for result in self.results],
        }

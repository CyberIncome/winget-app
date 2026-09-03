"""Registration and fail-closed aggregation for update providers."""

from __future__ import annotations

from collections.abc import Iterable

from src.providers.base import (
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderStatus,
    UpdateProvider,
    validate_provider_id,
)


def _failed_probe_status(provider_id: str, exc: Exception) -> ProviderStatus:
    """Create a diagnostic fallback when a provider cannot describe itself."""
    provider_id = validate_provider_id(provider_id)
    return ProviderStatus(
        provider_id=provider_id,
        display_name=provider_id,
        mode=ProviderMode.INFORMATIONAL,
        category=ProviderCategory.OTHER,
        available=False,
        reason=f"provider probe failed: {exc}",
    )


class ProviderRegistry:
    """Own a deterministic set of update providers keyed by provider id."""

    def __init__(self, providers: Iterable[UpdateProvider] | None = None):
        self._providers: dict[str, UpdateProvider] = {}
        for provider in providers or ():
            self.register(provider)

    def register(self, provider: UpdateProvider) -> None:
        """Register one provider, rejecting ambiguous duplicate ownership."""
        provider_id = validate_provider_id(provider.provider_id)
        if provider_id in self._providers:
            raise ValueError(f"duplicate provider id: {provider_id}")
        self._providers[provider_id] = provider

    def provider_ids(self) -> tuple[str, ...]:
        """Return provider ids in stable registration order."""
        return tuple(self._providers)

    def get(self, provider_id: str) -> UpdateProvider:
        """Return one provider or raise ``KeyError``."""
        return self._providers[validate_provider_id(provider_id)]

    def probe_all(self) -> tuple[ProviderStatus, ...]:
        """Probe all providers without turning one failure into global failure."""
        statuses = []
        for provider in self._providers.values():
            try:
                statuses.append(provider.probe())
            except Exception as exc:
                statuses.append(_failed_probe_status(provider.provider_id, exc))
        return tuple(statuses)

    def scan_all(
        self,
        provider_ids: Iterable[str] | None = None,
    ) -> tuple[ProviderScanResult, ...]:
        """Scan selected providers and keep failures provider-local."""
        if provider_ids is None:
            providers = list(self._providers.values())
        else:
            providers = [self.get(provider_id) for provider_id in provider_ids]

        results = []
        for provider in providers:
            try:
                status = provider.probe()
            except Exception as exc:
                status = _failed_probe_status(provider.provider_id, exc)
                results.append(
                    ProviderScanResult(
                        status=status,
                        error=status.reason,
                    )
                )
                continue

            if not status.available:
                results.append(ProviderScanResult(status=status))
                continue

            try:
                result = provider.scan_updates()
            except Exception as exc:
                results.append(
                    ProviderScanResult(
                        status=status,
                        error=f"provider scan failed: {exc}",
                    )
                )
                continue

            if result.status.provider_id != status.provider_id:
                results.append(
                    ProviderScanResult(
                        status=status,
                        error=(
                            "provider returned a scan result for a different "
                            "provider identity"
                        ),
                    )
                )
                continue

            invalid_owner = next(
                (
                    update
                    for update in result.updates
                    if update.provider_id != status.provider_id
                ),
                None,
            )
            if invalid_owner is not None:
                results.append(
                    ProviderScanResult(
                        status=status,
                        error=(
                            "provider returned an update owned by another "
                            f"provider: {invalid_owner.provider_id}"
                        ),
                    )
                )
                continue
            results.append(result)

        return tuple(results)

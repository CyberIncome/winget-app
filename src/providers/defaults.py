"""Default provider registry construction.

WinGet remains on the accepted GUI execution path during the migration. Its
provider adapter participates in read-only scans and exact action planning so
the eventual universal dashboard has one normalized provider model without
bypassing the already accepted WinGet controller.
"""

from __future__ import annotations

from src.providers.chocolatey import ChocolateyProvider
from src.providers.epic_legendary import EpicLegendaryProvider
from src.providers.npm import NpmGlobalProvider
from src.providers.pipx import PipxProvider
from src.providers.registry import ProviderRegistry
from src.providers.steam import SteamProvider
from src.providers.winget import WingetProvider


def build_default_provider_registry() -> ProviderRegistry:
    """Return the currently supported additive update providers."""
    return ProviderRegistry(
        [
            WingetProvider(),
            SteamProvider(),
            EpicLegendaryProvider(),
            ChocolateyProvider(),
            PipxProvider(),
            NpmGlobalProvider(),
        ]
    )

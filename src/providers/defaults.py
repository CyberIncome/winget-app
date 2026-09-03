"""Default provider registry construction.

WinGet remains on the accepted legacy execution path during the migration. The
providers registered here are additive and cannot replace Winget authority.
"""

from __future__ import annotations

from src.providers.chocolatey import ChocolateyProvider
from src.providers.npm import NpmGlobalProvider
from src.providers.pipx import PipxProvider
from src.providers.registry import ProviderRegistry
from src.providers.steam import SteamProvider


def build_default_provider_registry() -> ProviderRegistry:
    """Return the currently supported additive update providers."""
    return ProviderRegistry(
        [
            SteamProvider(),
            ChocolateyProvider(),
            PipxProvider(),
            NpmGlobalProvider(),
        ]
    )

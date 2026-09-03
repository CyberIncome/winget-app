"""Provider-based update discovery and execution contracts.

The provider layer lets the product aggregate update sources without letting one
provider impersonate another. Each provider owns its own identity, scan result,
authority mode, and update action.
"""

from src.providers.base import (
    ActionKind,
    ProviderAction,
    ProviderCapability,
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderStatus,
    ProviderUpdate,
    UpdateProvider,
)
from src.providers.registry import ProviderRegistry
from src.providers.snapshot import ProviderSnapshot

__all__ = [
    "ActionKind",
    "ProviderAction",
    "ProviderCapability",
    "ProviderCategory",
    "ProviderMode",
    "ProviderRegistry",
    "ProviderScanResult",
    "ProviderSnapshot",
    "ProviderStatus",
    "ProviderUpdate",
    "UpdateProvider",
]

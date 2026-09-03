"""Core contracts for update providers.

Providers are deliberately explicit about authority. A provider may directly
manage an update, hand the user to an owning launcher, or report information
only. The normalized records in this module never imply that one provider can
execute another provider's update.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Mapping, Protocol, runtime_checkable


_PROVIDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MAX_IDENTITY_LENGTH = 512


class ProviderMode(str, Enum):
    """How much authority a provider has over its update records."""

    MANAGED = "managed"
    HANDOFF = "handoff"
    INFORMATIONAL = "informational"


class ProviderCategory(str, Enum):
    """High-level update domain used for grouping and filtering."""

    APPLICATION = "application"
    GAME = "game"
    STORE = "store"
    SYSTEM = "system"
    DRIVER = "driver"
    FIRMWARE = "firmware"
    DEVELOPMENT = "development"
    EXTENSION = "extension"
    RUNTIME = "runtime"
    OTHER = "other"


class ProviderCapability(str, Enum):
    """A provider feature that the caller may rely on when advertised."""

    DETECT = "detect"
    UPDATE = "update"
    BULK_UPDATE = "bulk-update"
    PROGRESS = "progress"
    HANDOFF = "handoff"
    EXACT_TARGET = "exact-target"


class ActionKind(str, Enum):
    """Execution surface returned by a provider for one update."""

    COMMAND = "command"
    HANDOFF = "handoff"
    NONE = "none"


def _require_clean_text(value: str, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    if len(text) > _MAX_IDENTITY_LENGTH:
        raise ValueError(f"{field_name} exceeds {_MAX_IDENTITY_LENGTH} characters")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{field_name} contains control characters")
    return text


def validate_provider_id(value: str) -> str:
    """Return a normalized provider id or raise ``ValueError``."""
    provider_id = str(value or "").strip().lower()
    if not _PROVIDER_ID_RE.fullmatch(provider_id):
        raise ValueError(f"invalid provider id: {value!r}")
    return provider_id


@dataclass(frozen=True)
class ProviderStatus:
    """Availability and declared capabilities for one provider."""

    provider_id: str
    display_name: str
    mode: ProviderMode
    category: ProviderCategory
    available: bool
    capabilities: tuple[ProviderCapability, ...] = ()
    reason: str | None = None
    executable: str | None = None
    version: str | None = None
    requires_opt_in: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", validate_provider_id(self.provider_id))
        object.__setattr__(
            self,
            "display_name",
            _require_clean_text(self.display_name, field_name="display_name"),
        )
        if not self.available and not self.reason:
            object.__setattr__(self, "reason", "provider is not available")

    def to_dict(self) -> dict:
        """Return a JSON-serializable status record."""
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "mode": self.mode.value,
            "category": self.category.value,
            "available": self.available,
            "capabilities": [item.value for item in self.capabilities],
            "reason": self.reason,
            "executable": self.executable,
            "version": self.version,
            "requires_opt_in": self.requires_opt_in,
        }


@dataclass(frozen=True)
class ProviderUpdate:
    """Normalized update record owned by exactly one provider."""

    provider_id: str
    item_id: str
    name: str
    installed_version: str | None
    available_version: str | None
    category: ProviderCategory
    mode: ProviderMode
    can_update: bool
    source: str | None = None
    blocked_reason: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", validate_provider_id(self.provider_id))
        object.__setattr__(
            self,
            "item_id",
            _require_clean_text(self.item_id, field_name="item_id"),
        )
        object.__setattr__(
            self,
            "name",
            _require_clean_text(self.name, field_name="name"),
        )
        if self.mode != ProviderMode.MANAGED and self.can_update:
            raise ValueError(
                "only managed provider updates can claim direct execution"
            )
        if self.can_update and not self.available_version:
            raise ValueError("managed updates require an available target version")

    @property
    def identity(self) -> str:
        """Return a stable provider-scoped update identity."""
        return f"{self.provider_id}:{self.item_id.casefold()}"

    def to_dict(self) -> dict:
        """Return a JSON-serializable update record."""
        return {
            "provider_id": self.provider_id,
            "item_id": self.item_id,
            "name": self.name,
            "installed_version": self.installed_version,
            "available_version": self.available_version,
            "category": self.category.value,
            "mode": self.mode.value,
            "can_update": self.can_update,
            "source": self.source,
            "blocked_reason": self.blocked_reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProviderAction:
    """A provider-owned action for one normalized update record."""

    provider_id: str
    item_id: str
    kind: ActionKind
    target_version: str | None = None
    command: tuple[str, ...] = ()
    uri: str | None = None
    requires_elevation: bool = False
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", validate_provider_id(self.provider_id))
        object.__setattr__(
            self,
            "item_id",
            _require_clean_text(self.item_id, field_name="item_id"),
        )
        if self.kind == ActionKind.COMMAND:
            if not self.command:
                raise ValueError("command action requires a command")
            if not self.target_version:
                raise ValueError("command action requires an exact target version")
        elif self.command:
            raise ValueError("non-command action must not include command arguments")

        if self.kind == ActionKind.HANDOFF:
            if not self.uri:
                raise ValueError("handoff action requires a URI")
        elif self.uri:
            raise ValueError("non-handoff action must not include a URI")


@dataclass(frozen=True)
class ProviderScanResult:
    """One provider scan outcome without conflating failure with no updates."""

    status: ProviderStatus
    updates: tuple[ProviderUpdate, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict:
        """Return a JSON-serializable scan result."""
        return {
            "status": self.status.to_dict(),
            "updates": [item.to_dict() for item in self.updates],
            "warnings": list(self.warnings),
            "error": self.error,
        }


@runtime_checkable
class UpdateProvider(Protocol):
    """Protocol implemented by every update provider."""

    provider_id: str

    def probe(self) -> ProviderStatus:
        """Return availability/capabilities without mutating the system."""

    def scan_updates(self) -> ProviderScanResult:
        """Return a read-only update snapshot."""

    def plan_update(self, update: ProviderUpdate) -> ProviderAction:
        """Return the exact provider-owned action for one update."""

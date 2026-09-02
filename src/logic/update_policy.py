"""Persistent user policy for hiding package updates without weakening targeting."""

from __future__ import annotations


_MAX_IDENTITY_LENGTH = 1024


def package_identity(item: dict) -> str | None:
    """Return a stable source-aware identity for an update row."""
    source = str(item.get("Source") or "").strip().casefold()
    package_id = str(item.get("Id") or "").strip().casefold()
    if package_id:
        value = f"id:{package_id}|source:{source}"
    else:
        name = str(item.get("Name") or "").strip().casefold()
        if not name:
            return None
        value = f"name:{name}|source:{source}"
    return value if len(value) <= _MAX_IDENTITY_LENGTH else None


def update_skip_identity(item: dict) -> str | None:
    """Return an identity for one specific offered update version."""
    base = package_identity(item)
    available = str(item.get("Available") or "").strip().casefold()
    if not base or not available:
        return None
    value = f"{base}|available:{available}"
    return value if len(value) <= _MAX_IDENTITY_LENGTH else None


def normalize_ignored_updates(values) -> list[str]:
    """Normalize both legacy package-wide and version-specific ignore keys."""
    if not isinstance(values, list):
        return []
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().casefold()
        if (
            not normalized
            or len(normalized) > _MAX_IDENTITY_LENGTH
            or normalized in seen
        ):
            continue
        if not (
            normalized.startswith("id:")
            or normalized.startswith("name:")
        ):
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def is_update_ignored(item: dict, ignored_values) -> bool:
    ignored = set(normalize_ignored_updates(ignored_values))
    package_key = package_identity(item)
    version_key = update_skip_identity(item)
    # Package-only identities are retained for backward compatibility and for
    # advanced users who may have intentionally persisted a permanent ignore.
    return bool(
        (package_key and package_key in ignored)
        or (version_key and version_key in ignored)
    )


def filter_ignored_updates(
    items: list[dict], ignored_values
) -> tuple[list[dict], int]:
    ignored = set(normalize_ignored_updates(ignored_values))
    kept = []
    removed = 0
    for item in items or []:
        package_key = package_identity(item)
        version_key = update_skip_identity(item)
        if (
            (package_key and package_key in ignored)
            or (version_key and version_key in ignored)
        ):
            removed += 1
        else:
            kept.append(item)
    return kept, removed

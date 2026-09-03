"""Small strict Semantic Versioning parser used by runtime product features."""

from __future__ import annotations

from dataclasses import dataclass
import re


_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)
_IDENTIFIER_RE = re.compile(r"^[0-9A-Za-z-]+$")


@dataclass(frozen=True)
class SemVer:
    core: tuple[int, int, int]
    prerelease: tuple[str, ...] | None
    build: tuple[str, ...] | None


def _identifiers(value: str | None, *, prerelease: bool) -> tuple[str, ...] | None:
    if value is None:
        return None
    result = tuple(value.split("."))
    for identifier in result:
        if not identifier or not _IDENTIFIER_RE.fullmatch(identifier):
            raise ValueError("invalid semantic-version identifier")
        if (
            prerelease
            and identifier.isdigit()
            and len(identifier) > 1
            and identifier.startswith("0")
        ):
            raise ValueError(
                "numeric prerelease identifiers cannot contain leading zeros"
            )
    return result


def parse_semver(value: str) -> SemVer:
    text = str(value or "").strip()
    match = _SEMVER_RE.fullmatch(text)
    if not match:
        raise ValueError(f"invalid semantic version: {value!r}")
    return SemVer(
        core=(int(match.group(1)), int(match.group(2)), int(match.group(3))),
        prerelease=_identifiers(match.group(4), prerelease=True),
        build=_identifiers(match.group(5), prerelease=False),
    )


def is_valid_semver(value: str) -> bool:
    try:
        parse_semver(value)
    except ValueError:
        return False
    return True


def compare_semver(left: str, right: str) -> int:
    """Return -1/0/1 using SemVer precedence; build metadata is ignored."""
    a = parse_semver(left)
    b = parse_semver(right)
    if a.core != b.core:
        return -1 if a.core < b.core else 1
    if a.prerelease is None and b.prerelease is None:
        return 0
    if a.prerelease is None:
        return 1
    if b.prerelease is None:
        return -1

    for left_id, right_id in zip(a.prerelease, b.prerelease):
        if left_id == right_id:
            continue
        left_numeric = left_id.isdigit()
        right_numeric = right_id.isdigit()
        if left_numeric and right_numeric:
            return -1 if int(left_id) < int(right_id) else 1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return -1 if left_id < right_id else 1

    if len(a.prerelease) == len(b.prerelease):
        return 0
    return -1 if len(a.prerelease) < len(b.prerelease) else 1

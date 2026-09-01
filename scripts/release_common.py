"""Shared release/version helpers for local Windows packaging."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import struct


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
VERSION_FILE = ROOT / "VERSION"
BUILD_VERSION_FILE = DIST_DIR / "BUILD_VERSION"

_CORE_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(.*)$")
_IDENTIFIER_RE = re.compile(r"^[0-9A-Za-z-]+$")
_MAX_WINDOWS_VERSION_PART = 65535


def _validate_identifiers(value: str, *, numeric_leading_zero: bool) -> None:
    for identifier in value.split("."):
        if not identifier or not _IDENTIFIER_RE.fullmatch(identifier):
            raise ValueError("invalid semantic-version identifier")
        if (
            numeric_leading_zero
            and identifier.isdigit()
            and len(identifier) > 1
            and identifier.startswith("0")
        ):
            raise ValueError("numeric prerelease identifiers cannot have leading zeros")


def parse_version(value: str) -> tuple[str, tuple[int, int, int, int]]:
    """Validate SemVer release text and return public/numeric Windows versions."""
    version = value.strip()
    match = _CORE_RE.fullmatch(version)
    if not match:
        raise ValueError(
            "VERSION must use semantic versioning such as 1.0.0 or 1.2.3-rc.1"
        )

    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    if any(part > _MAX_WINDOWS_VERSION_PART for part in (major, minor, patch)):
        raise ValueError("VERSION components must be <= 65535 for Windows metadata")

    suffix = match.group(4)
    prerelease = ""
    build = ""
    if suffix:
        remaining = suffix
        if remaining.startswith("-"):
            remaining = remaining[1:]
            prerelease, separator, build = remaining.partition("+")
            _validate_identifiers(prerelease, numeric_leading_zero=True)
            if separator:
                _validate_identifiers(build, numeric_leading_zero=False)
        elif remaining.startswith("+"):
            build = remaining[1:]
            _validate_identifiers(build, numeric_leading_zero=False)
        else:
            raise ValueError("invalid semantic-version suffix")

    return version, (major, minor, patch, 0)


def read_version() -> tuple[str, tuple[int, int, int, int]]:
    """Read the repository's single source of release version truth."""
    if not VERSION_FILE.is_file():
        raise FileNotFoundError(f"Missing release version file: {VERSION_FILE}")
    return parse_version(VERSION_FILE.read_text(encoding="utf-8"))


def numeric_version_text(numeric: tuple[int, int, int, int]) -> str:
    return ".".join(str(part) for part in numeric)


def write_build_version(version: str) -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    return BUILD_VERSION_FILE


def require_build_version(expected_version: str) -> None:
    if not BUILD_VERSION_FILE.is_file():
        raise FileNotFoundError(
            f"Missing {BUILD_VERSION_FILE}; rebuild the PyInstaller artifacts first."
        )
    actual = BUILD_VERSION_FILE.read_text(encoding="utf-8").strip()
    if actual != expected_version:
        raise ValueError(
            f"Packaged artifacts were built for {actual!r}, expected {expected_version!r}. "
            "Rebuild before creating or publishing a release."
        )


def require_files(paths: list[Path]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required artifact(s): " + ", ".join(missing))


def pe_machine(path: Path) -> int:
    """Return the PE COFF machine value without loading/executing the file."""
    with path.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise ValueError(f"Not a PE executable: {path}")
        handle.seek(0x3C)
        offset_raw = handle.read(4)
        if len(offset_raw) != 4:
            raise ValueError(f"Truncated PE header: {path}")
        pe_offset = struct.unpack("<I", offset_raw)[0]
        handle.seek(pe_offset)
        if handle.read(4) != b"PE\0\0":
            raise ValueError(f"Invalid PE signature: {path}")
        machine_raw = handle.read(2)
        if len(machine_raw) != 2:
            raise ValueError(f"Missing PE machine field: {path}")
        return struct.unpack("<H", machine_raw)[0]


def require_x64_pe(paths: list[Path]) -> None:
    """Require AMD64/x64 PE binaries (IMAGE_FILE_MACHINE_AMD64)."""
    require_files(paths)
    wrong = []
    for path in paths:
        try:
            machine = pe_machine(path)
        except (OSError, ValueError) as exc:
            wrong.append(f"{path}: {exc}")
            continue
        if machine != 0x8664:
            wrong.append(f"{path}: PE machine 0x{machine:04X}, expected 0x8664")
    if wrong:
        raise ValueError("Non-x64 release artifact(s): " + "; ".join(wrong))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256_manifest(paths: list[Path], destination: Path) -> Path:
    require_files(paths)
    lines = [f"{sha256_file(path)}  {path.name}" for path in paths]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination

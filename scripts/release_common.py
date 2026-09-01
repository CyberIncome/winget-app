"""Shared release/version helpers for local Windows packaging."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import struct


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
VERSION_FILE = ROOT / "VERSION"

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)


def parse_version(value: str) -> tuple[str, tuple[int, int, int, int]]:
    """Validate release text and return public/numeric versions."""
    version = value.strip()
    match = _SEMVER_RE.fullmatch(version)
    if not match:
        raise ValueError(
            "VERSION must use semantic versioning such as 1.0.0 or 1.2.3-rc.1"
        )
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    return version, (major, minor, patch, 0)


def read_version() -> tuple[str, tuple[int, int, int, int]]:
    """Read the repository's single source of release version truth."""
    if not VERSION_FILE.is_file():
        raise FileNotFoundError(f"Missing release version file: {VERSION_FILE}")
    return parse_version(VERSION_FILE.read_text(encoding="utf-8"))


def numeric_version_text(numeric: tuple[int, int, int, int]) -> str:
    return ".".join(str(part) for part in numeric)


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

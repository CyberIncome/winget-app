"""Shared release/version helpers for local Windows packaging."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
VERSION_FILE = ROOT / "VERSION"

GUI_EXE = DIST_DIR / "WingetUniversalDashboard.exe"
CLI_EXE = DIST_DIR / "WingetUniversalDashboardCLI.exe"
SETUP_EXE = DIST_DIR / "WingetUniversalDashboard-Setup-x64.exe"
BUILD_INFO_FILE = DIST_DIR / "BUILD_INFO.json"
CHECKSUMS_FILE = DIST_DIR / "SHA256SUMS.txt"

HASHED_RELEASE_ASSETS = (SETUP_EXE, GUI_EXE, CLI_EXE, BUILD_INFO_FILE)
UPLOAD_RELEASE_ASSETS = (*HASHED_RELEASE_ASSETS, CHECKSUMS_FILE)

_CORE_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(.*)$")
_IDENTIFIER_RE = re.compile(r"^[0-9A-Za-z-]+$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
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
    if suffix:
        remaining = suffix
        if remaining.startswith("-"):
            remaining = remaining[1:]
            prerelease, separator, build = remaining.partition("+")
            _validate_identifiers(prerelease, numeric_leading_zero=True)
            if separator:
                _validate_identifiers(build, numeric_leading_zero=False)
        elif remaining.startswith("+"):
            _validate_identifiers(remaining[1:], numeric_leading_zero=False)
        else:
            raise ValueError("invalid semantic-version suffix")

    return version, (major, minor, patch, 0)


def is_prerelease(version: str) -> bool:
    """Return whether a validated SemVer includes a prerelease component."""
    parsed, _numeric = parse_version(version)
    return "-" in parsed.split("+", 1)[0]


def read_version() -> tuple[str, tuple[int, int, int, int]]:
    """Read the repository's single source of release version truth."""
    if not VERSION_FILE.is_file():
        raise FileNotFoundError(f"Missing release version file: {VERSION_FILE}")
    return parse_version(VERSION_FILE.read_text(encoding="utf-8"))


def numeric_version_text(numeric: tuple[int, int, int, int]) -> str:
    return ".".join(str(part) for part in numeric)


def _capture_git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments], cwd=ROOT, text=True, stderr=subprocess.STDOUT
    ).strip()


def current_git_commit() -> str:
    commit = _capture_git("rev-parse", "HEAD")
    if not _GIT_COMMIT_RE.fullmatch(commit):
        raise RuntimeError(f"Unexpected Git commit identifier: {commit!r}")
    return commit.lower()


def current_git_branch() -> str:
    return _capture_git("branch", "--show-current")


def worktree_is_dirty() -> bool:
    return bool(_capture_git("status", "--porcelain"))


def require_clean_worktree() -> str:
    if worktree_is_dirty():
        raise RuntimeError("Refusing release build from a dirty working tree.")
    return current_git_commit()


def write_build_identity(version: str, commit: str, *, dirty: bool) -> Path:
    """Record source identity for the portable artifacts."""
    parse_version(version)
    if not _GIT_COMMIT_RE.fullmatch(commit):
        raise ValueError(f"Invalid Git commit identifier: {commit!r}")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": version,
        "commit": commit.lower(),
        "dirty": bool(dirty),
    }
    BUILD_INFO_FILE.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return BUILD_INFO_FILE


def read_build_identity() -> dict[str, object]:
    if not BUILD_INFO_FILE.is_file():
        raise FileNotFoundError(
            f"Missing {BUILD_INFO_FILE}; rebuild the PyInstaller artifacts first."
        )
    try:
        payload = json.loads(BUILD_INFO_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid build identity file: {BUILD_INFO_FILE}") from exc
    if not isinstance(payload, dict) or set(payload) != {"version", "commit", "dirty"}:
        raise ValueError(f"Invalid build identity file: {BUILD_INFO_FILE}")
    if not isinstance(payload["version"], str):
        raise ValueError(f"Invalid build identity version in: {BUILD_INFO_FILE}")
    parse_version(payload["version"])
    if not isinstance(payload["commit"], str) or not _GIT_COMMIT_RE.fullmatch(
        payload["commit"]
    ):
        raise ValueError(f"Invalid build identity commit in: {BUILD_INFO_FILE}")
    if type(payload["dirty"]) is not bool:
        raise ValueError(f"Invalid build identity dirty flag in: {BUILD_INFO_FILE}")
    return payload


def require_build_identity(expected_version: str, expected_commit: str) -> None:
    """Require clean artifacts built from this exact version and commit."""
    payload = read_build_identity()
    if payload["dirty"] is not False:
        raise ValueError("Release artifacts were built from a dirty working tree.")
    if (
        payload["version"] != expected_version
        or str(payload["commit"]).lower() != expected_commit.lower()
    ):
        raise ValueError(
            "Release artifacts do not match the current source identity: "
            f"built version/commit={payload['version']!r}/{payload['commit']!r}, "
            f"expected={expected_version!r}/{expected_commit!r}. Rebuild first."
        )


def require_files(paths: list[Path] | tuple[Path, ...]) -> None:
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


def require_x64_pe(paths: list[Path] | tuple[Path, ...]) -> None:
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


def _sha256_manifest_text(paths: list[Path] | tuple[Path, ...]) -> str:
    require_files(paths)
    return "\n".join(f"{sha256_file(path)}  {path.name}" for path in paths) + "\n"


def write_sha256_manifest(
    paths: list[Path] | tuple[Path, ...], destination: Path
) -> Path:
    destination.write_text(_sha256_manifest_text(paths), encoding="utf-8")
    return destination


def verify_sha256_manifest(
    paths: list[Path] | tuple[Path, ...], manifest: Path
) -> None:
    if not manifest.is_file():
        raise FileNotFoundError(f"Missing checksum manifest: {manifest}")
    expected = _sha256_manifest_text(paths)
    actual = manifest.read_text(encoding="utf-8")
    if actual != expected:
        raise ValueError("SHA256SUMS.txt does not match the release artifacts.")

"""Release/installer tooling contracts that do not require Windows tooling."""

from __future__ import annotations

from pathlib import Path
import struct
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import release_common  # noqa: E402
from release_common import (  # noqa: E402
    numeric_version_text,
    parse_version,
    pe_machine,
    require_build_version,
    require_x64_pe,
    write_build_version,
)


def test_version_file_is_valid_semver():
    version, numeric = parse_version((ROOT / "VERSION").read_text(encoding="utf-8"))
    raw = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version == raw
    core = tuple(
        int(part)
        for part in version.split("-", 1)[0].split("+", 1)[0].split(".")
    )
    assert numeric == (*core, 0)
    assert numeric_version_text(numeric) == ".".join(
        str(part) for part in (*core, 0)
    )


def test_prerelease_keeps_text_and_numeric_windows_version():
    assert parse_version("1.2.3-rc.1") == ("1.2.3-rc.1", (1, 2, 3, 0))
    assert parse_version("1.2.3+build.7") == ("1.2.3+build.7", (1, 2, 3, 0))


@pytest.mark.parametrize(
    "value",
    [
        "",
        "v1.0.0",
        "1.0",
        "01.0.0",
        "1.0.0\njunk",
        "1.0.0/unsafe",
        "1.0.0-01",
        "1.0.0-alpha..1",
        "1.0.0+build..1",
        "65536.0.0",
    ],
)
def test_release_version_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_version(value)


def test_build_version_marker_prevents_stale_artifacts(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    marker = dist / "BUILD_VERSION"
    monkeypatch.setattr(release_common, "DIST_DIR", dist)
    monkeypatch.setattr(release_common, "BUILD_VERSION_FILE", marker)

    write_build_version("1.2.3")
    require_build_version("1.2.3")
    with pytest.raises(ValueError):
        require_build_version("1.2.4")


def _write_pe(path: Path, machine: int) -> None:
    data = bytearray(0x90)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, machine)
    path.write_bytes(data)


def test_x64_pe_validation(tmp_path):
    amd64 = tmp_path / "amd64.exe"
    x86 = tmp_path / "x86.exe"
    _write_pe(amd64, 0x8664)
    _write_pe(x86, 0x014C)

    assert pe_machine(amd64) == 0x8664
    require_x64_pe([amd64])
    with pytest.raises(ValueError):
        require_x64_pe([x86])


def test_inno_script_is_true_x64_per_user_and_stable_id():
    source = (ROOT / "installer" / "WingetUniversalDashboard.iss").read_text(
        encoding="utf-8"
    )
    assert "AppId={{C41A014A-142E-43E7-AB8F-07AC4479E07F}" in source
    assert "SetupArchitecture=x64" in source
    assert "ArchitecturesAllowed=x64compatible" in source
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in source
    assert "DefaultDirName={localappdata}\\Programs\\WingetUniversalDashboard" in source
    assert "PrivilegesRequired=lowest" in source
    assert "WingetUniversalDashboardCLI.exe" in source
    assert "OutputBaseFilename=WingetUniversalDashboard-Setup-x64" in source
    assert "VersionInfoVersion={#AppVersionNumeric}" in source
    assert "VersionInfoProductVersion={#AppVersionNumeric}" in source
    assert "VersionInfoProductTextVersion={#AppVersion}" in source


def test_build_scripts_require_matching_x64_artifacts():
    windows_source = (SCRIPTS / "build_windows.py").read_text(encoding="utf-8")
    installer_source = (SCRIPTS / "build_installer.py").read_text(encoding="utf-8")
    assert "require_x64_pe(artifacts)" in windows_source
    assert "write_build_version(version)" in windows_source
    assert "require_build_version(version)" in installer_source
    assert "require_x64_pe([SETUP_EXE])" in installer_source


def test_release_builder_emits_checksums_and_installer():
    source = (SCRIPTS / "build_release.py").read_text(encoding="utf-8")
    assert "build_installer.py" in source
    assert "SHA256SUMS.txt" in source
    assert "write_sha256_manifest" in source


def test_publisher_defaults_to_draft_requires_clean_master_and_matches_version():
    source = (SCRIPTS / "publish_release.py").read_text(encoding="utf-8")
    assert '"--draft"' in source
    assert "Refusing to publish from a dirty working tree." in source
    assert "merge to master first" in source
    assert '"--target"' in source
    assert "require_build_version(version)" in source
    assert 'if args.prerelease or "-" in version:' in source


def test_installer_smoke_uses_temporary_directory_and_uninstalls():
    source = (SCRIPTS / "smoke_installer.py").read_text(encoding="utf-8")
    assert "TemporaryDirectory" in source
    assert "/CURRENTUSER" in source
    assert "/NOICONS" in source
    assert "unins*.exe" in source
    assert "WUD_PACKAGED_SMOKE" in source

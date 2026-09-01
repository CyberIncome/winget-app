"""Release/installer tooling contracts that do not require Windows tooling."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import release_common  # noqa: E402
from release_common import is_prerelease, numeric_version_text, parse_version  # noqa: E402


def test_version_file_is_valid_semver():
    version, numeric = parse_version((ROOT / "VERSION").read_text(encoding="utf-8"))
    raw = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version == raw
    core = tuple(
        int(part)
        for part in version.split("-", 1)[0].split("+", 1)[0].split(".")
    )
    assert numeric == (*core, 0)
    assert numeric_version_text(numeric) == ".".join(str(part) for part in (*core, 0))


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
        "65536.0.0",
    ],
)
def test_release_version_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_version(value)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.0.0", False),
        ("1.0.0+build.5", False),
        ("1.0.0-rc.1", True),
        ("1.0.0-rc.1+build.5", True),
    ],
)
def test_prerelease_detection(version, expected):
    assert is_prerelease(version) is expected


def test_build_identity_requires_exact_clean_version_and_commit(tmp_path, monkeypatch):
    build_info = tmp_path / "BUILD_INFO.json"
    monkeypatch.setattr(release_common, "BUILD_INFO_FILE", build_info)

    commit = "a" * 40
    release_common.write_build_identity("1.2.3", commit, dirty=False)
    release_common.require_build_identity("1.2.3", commit)

    with pytest.raises(ValueError):
        release_common.require_build_identity("1.2.4", commit)
    with pytest.raises(ValueError):
        release_common.require_build_identity("1.2.3", "b" * 40)

    payload = json.loads(build_info.read_text(encoding="utf-8"))
    payload["dirty"] = True
    build_info.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="dirty"):
        release_common.require_build_identity("1.2.3", commit)


def test_checksum_manifest_detects_changed_artifact(tmp_path):
    first = tmp_path / "first.exe"
    second = tmp_path / "second.exe"
    manifest = tmp_path / "SHA256SUMS.txt"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    release_common.write_sha256_manifest((first, second), manifest)
    release_common.verify_sha256_manifest((first, second), manifest)

    second.write_bytes(b"changed")
    with pytest.raises(ValueError, match="does not match"):
        release_common.verify_sha256_manifest((first, second), manifest)


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
    assert "BUILD_INFO.json" in source
    assert "OutputBaseFilename=WingetUniversalDashboard-Setup-x64" in source
    assert "VersionInfoVersion={#AppVersionNumeric}" in source
    assert "VersionInfoProductVersion={#AppVersionNumeric}" in source
    assert "VersionInfoProductTextVersion={#AppVersion}" in source


def test_release_builder_requires_clean_identity_and_emits_checksums():
    source = (SCRIPTS / "build_release.py").read_text(encoding="utf-8")
    assert "require_clean_worktree" in source
    assert "require_build_identity" in source
    assert "build_installer.py" in source
    assert "HASHED_RELEASE_ASSETS" in source
    assert "write_sha256_manifest" in source
    assert "verify_sha256_manifest" in source


def test_portable_builder_records_commit_and_dirty_state():
    source = (SCRIPTS / "build_windows.py").read_text(encoding="utf-8")
    assert "current_git_commit()" in source
    assert "worktree_is_dirty()" in source
    assert "write_build_identity(version, commit, dirty=dirty)" in source


def test_installer_builder_requires_clean_matching_artifacts_and_inno_7():
    source = (SCRIPTS / "build_installer.py").read_text(encoding="utf-8")
    assert "require_clean_worktree()" in source
    assert "require_build_identity(version, commit)" in source
    assert '"Inno Setup 7"' in source
    assert "require_x64_pe([SETUP_EXE])" in source


def test_publisher_verifies_commit_hashes_remote_and_defaults_draft():
    source = (SCRIPTS / "publish_release.py").read_text(encoding="utf-8")
    assert '"--draft"' in source
    assert "require_build_identity(version, head)" in source
    assert "verify_sha256_manifest(HASHED_RELEASE_ASSETS, CHECKSUMS_FILE)" in source
    assert '"ls-remote"' in source
    assert "does not match origin/" in source
    assert "Remote tag" in source
    assert "is_prerelease(version)" in source
    assert 'branch != "master"' in source


def test_installer_smoke_refuses_existing_install_and_uninstalls():
    source = (SCRIPTS / "smoke_installer.py").read_text(encoding="utf-8")
    assert "TemporaryDirectory" in source
    assert "_require_no_existing_install()" in source
    assert "HKEY_CURRENT_USER" in source
    assert "/CURRENTUSER" in source
    assert "/NOICONS" in source
    assert "unins*.exe" in source
    assert "WUD_PACKAGED_SMOKE" in source
    assert "BUILD_INFO.json" in source

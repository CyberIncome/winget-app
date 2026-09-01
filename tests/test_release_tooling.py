"""Release/installer tooling contracts that do not require Windows tooling."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from release_common import numeric_version_text, parse_version  # noqa: E402


def test_version_file_is_valid_semver():
    version, numeric = parse_version((ROOT / "VERSION").read_text(encoding="utf-8"))
    assert version == "1.0.0"
    assert numeric == (1, 0, 0, 0)
    assert numeric_version_text(numeric) == "1.0.0.0"


@pytest.mark.parametrize(
    "value",
    ["", "v1.0.0", "1.0", "01.0.0", "1.0.0\njunk", "1.0.0/unsafe"],
)
def test_release_version_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_version(value)


def test_inno_script_is_x64compatible_per_user_and_stable_id():
    source = (ROOT / "installer" / "WingetUniversalDashboard.iss").read_text(
        encoding="utf-8"
    )
    assert "AppId={{C41A014A-142E-43E7-AB8F-07AC4479E07F}" in source
    assert "ArchitecturesAllowed=x64compatible" in source
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in source
    assert "DefaultDirName={localappdata}\\Programs\\WingetUniversalDashboard" in source
    assert "PrivilegesRequired=lowest" in source
    assert "WingetUniversalDashboardCLI.exe" in source
    assert "OutputBaseFilename=WingetUniversalDashboard-Setup-x64" in source


def test_release_builder_emits_checksums_and_installer():
    source = (SCRIPTS / "build_release.py").read_text(encoding="utf-8")
    assert "build_installer.py" in source
    assert "SHA256SUMS.txt" in source
    assert "write_sha256_manifest" in source


def test_publisher_defaults_to_draft_and_requires_clean_master():
    source = (SCRIPTS / "publish_release.py").read_text(encoding="utf-8")
    assert '"--draft"' in source
    assert "Refusing to publish from a dirty working tree." in source
    assert "merge to master first" in source
    assert '"--target"' in source


def test_installer_smoke_uses_temporary_directory_and_uninstalls():
    source = (SCRIPTS / "smoke_installer.py").read_text(encoding="utf-8")
    assert "TemporaryDirectory" in source
    assert "/CURRENTUSER" in source
    assert "/NOICONS" in source
    assert "unins*.exe" in source
    assert "WUD_PACKAGED_SMOKE" in source

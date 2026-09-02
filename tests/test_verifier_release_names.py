"""Source contract ensuring Windows verification follows public release names."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_verifier_uses_release_common_artifact_names():
    source = (ROOT / "scripts" / "verify_windows.py").read_text(encoding="utf-8")
    assert "from release_common import CLI_EXE, GUI_EXE" in source
    assert "gui_artifact = GUI_EXE" in source
    assert "cli_artifact = CLI_EXE" in source
    assert 'ROOT / "dist" / "WingetUniversalDashboard.exe"' not in source
    assert 'ROOT / "dist" / "WingetUniversalDashboardCLI.exe"' not in source

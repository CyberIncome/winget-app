"""Source contracts for conservative version-target execution guards."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_incomplete_scan_targets_are_review_only():
    source = (ROOT / "src" / "ui" / "version_integrity_window.py").read_text(
        encoding="utf-8"
    )
    assert 'lowered in {"unknown", "???"}' in source
    assert '"…" in text or text.endswith("...")' in source
    assert 'item["VersionStatus"] = "incomplete-target"' in source
    assert "no update command will be generated" in source
    assert "if not self._complete_scan_target(item.get(\"Available\"))" in source


def test_mapping_review_confirmation_cannot_be_disabled():
    source = (ROOT / "src" / "ui" / "version_integrity_window.py").read_text(
        encoding="utf-8"
    )
    assert "Confirm Version-Mapping Update" in source
    assert "review_count = self._refs_requiring_version_review(package_refs)" in source
    assert "if not review_count:" in source
    assert "ConfigManager().confirm_updates" not in source
    assert "exact WinGet package versions shown" in source

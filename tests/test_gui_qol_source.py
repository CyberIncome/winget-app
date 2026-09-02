"""Source contracts for additive GUI quality-of-life behavior."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_update_page_adds_filter_summary_and_explicit_selection_controls():
    source = (ROOT / "src" / "ui" / "version_integrity_window.py").read_text(
        encoding="utf-8"
    )
    assert "Select Visible Rows" in source
    assert "Clear Selection" in source
    assert "Clear Search" in source
    assert "shown /" in source
    assert "version mapping review" in source
    assert "Detective informational" in source


def test_double_click_is_read_only_for_updates_and_inventory():
    version_source = (ROOT / "src" / "ui" / "version_aware_window.py").read_text(
        encoding="utf-8"
    )
    integrity_source = (
        ROOT / "src" / "ui" / "version_integrity_window.py"
    ).read_text(encoding="utf-8")
    assert "doubleClicked.disconnect" in version_source
    assert "_double_click_package_details" in version_source
    assert "self.inventory_table.doubleClicked.disconnect()" in integrity_source
    assert "handle_table_click(self.inventory_table, index)" in integrity_source


def test_update_table_explains_mixed_target_provenance():
    source = (ROOT / "src" / "ui" / "version_integrity_window.py").read_text(
        encoding="utf-8"
    )
    assert "Installed (Windows) is the Apps & Features/ARP display version" in source
    assert 'model.headers[4] = "Reported Target"' in source
    assert "Target (WinGet package)" in source
    assert "Reported remote target (Detective)" in source
    assert "This row cannot trigger a WinGet package update" in source
    assert "Double-click = read-only details" in source

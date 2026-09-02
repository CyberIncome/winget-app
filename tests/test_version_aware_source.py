"""Source-level contracts for version provenance and exact-target GUI behavior."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_entrypoints_use_version_aware_window():
    main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    smoke_source = (ROOT / "scripts" / "smoke_gui.py").read_text(encoding="utf-8")
    assert "from src.ui.version_aware_window import VersionAwareMainWindow" in main_source
    assert "window = VersionAwareMainWindow()" in main_source
    assert "from src.ui.version_aware_window import VersionAwareMainWindow" in smoke_source
    assert "window = VersionAwareMainWindow()" in smoke_source


def test_version_layer_is_above_workbench_and_reconciles_non_blockingly():
    source = (ROOT / "src" / "ui" / "version_aware_window.py").read_text(
        encoding="utf-8"
    )
    assert "class VersionAwareMainWindow(WorkbenchMainWindow)" in source
    assert '"version-map"' in source
    assert "winget_version_map_worker" in source
    assert "merge_export_versions" in source
    assert "Version mapping review" in source
    assert '"Installed (Windows)"' in source
    assert '"Target (WinGet)"' in source
    assert "doubleClicked.disconnect" in source
    assert "exact_package_show_worker" in source


def test_gui_refs_and_execution_bind_exact_scan_target():
    source = (ROOT / "src" / "ui" / "version_aware_window.py").read_text(
        encoding="utf-8"
    )
    assert 'target_version = validate_package_version(item.get("Available"))' in source
    assert 'ref["version"] = target_version' in source
    assert 'version=target_version' in source
    assert 'str(ref.get("version") or "").casefold()' in source
    assert "exact target versions shown" in source


def test_version_worker_uses_include_versions_export_and_exact_show():
    source = (ROOT / "src" / "logic" / "version_workers.py").read_text(
        encoding="utf-8"
    )
    assert "include_versions=True" in source
    assert "extract_export_version_records" in source
    assert 'version=ref.get("version")' in source
    assert "result.stdout[:256 * 1024]" in source

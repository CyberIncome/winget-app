"""Source-level contracts for version provenance and exact-target GUI behavior."""

from pathlib import Path

from src.logic.update_batch import BatchResultTracker


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_entrypoints_use_version_integrity_window():
    main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    smoke_source = (ROOT / "scripts" / "smoke_gui.py").read_text(encoding="utf-8")
    assert "from src.ui.version_integrity_window import VersionIntegrityMainWindow" in main_source
    assert "window = VersionIntegrityMainWindow()" in main_source
    assert "from src.ui.version_integrity_window import VersionIntegrityMainWindow" in smoke_source
    assert "window = VersionIntegrityMainWindow()" in smoke_source


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


def test_integrity_layer_restarts_after_finished_and_removes_exact_target_only():
    source = (ROOT / "src" / "ui" / "version_integrity_window.py").read_text(
        encoding="utf-8"
    )
    assert "class VersionIntegrityMainWindow(VersionAwareMainWindow)" in source
    assert "def _handle_job_finished" in source
    assert "super()._handle_job_finished(name)" in source
    assert 'name == "version-map" and self._version_reconcile_pending' in source
    assert "def remove_package_from_model" in source
    assert 'package_ref.get("version")' in source
    assert 'item.get("Available")' in source
    assert "preserving the newer/different row" in source


def test_batch_tracking_distinguishes_same_package_different_target_versions():
    first = {
        "match_by": "id",
        "value": "Vendor.App",
        "source": "winget",
        "version": "1.2.3",
    }
    second = {**first, "version": "1.2.4"}
    tracker = BatchResultTracker([first, second])
    assert tracker.requested_count == 2
    tracker.record_success(first)
    summary = tracker.summary()
    assert summary["succeeded"] == 1
    assert summary["pending"] == 1
    assert summary["pending_refs"][0]["version"] == "1.2.4"

"""Source contracts for interactive workbench behavior."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workbench_remains_below_version_layer():
    workbench = (ROOT / "src" / "ui" / "workbench_window.py").read_text(
        encoding="utf-8"
    )
    version_aware = (ROOT / "src" / "ui" / "version_aware_window.py").read_text(
        encoding="utf-8"
    )
    assert "class WorkbenchMainWindow(ProductMainWindow)" in workbench
    assert "class VersionAwareMainWindow(WorkbenchMainWindow)" in version_aware


def test_workbench_adds_managed_read_only_package_tools_and_cancel():
    source = (ROOT / "src" / "ui" / "workbench_window.py").read_text(
        encoding="utf-8"
    )
    assert "class WorkbenchMainWindow(ProductMainWindow)" in source
    assert '"winget-export"' in source
    assert "winget_export_worker" in source
    assert '"package-show"' in source
    assert "package_show_worker" in source
    assert "Export WinGet Restore List" in source
    assert "View WinGet Package Details" in source
    assert "Skip This Update Version" in source
    assert "Cancel Update Batch" in source
    assert "_stop_qprocess_safely" in source
    assert '"cancelled by user"' in source
    assert '"failed before process start"' in source


def test_workers_validate_and_atomically_publish_export_and_bound_show_output():
    source = (ROOT / "src" / "logic" / "worker_jobs.py").read_text(
        encoding="utf-8"
    )
    assert "package_show_worker" in source
    assert "result.stdout[:256 * 1024]" in source
    assert "winget_export_worker" in source
    assert "json.loads" in source
    assert "16 * 1024 * 1024" in source
    assert ".wud-export-" in source
    assert ".tmp.json" in source
    assert "os.replace(temporary, destination)" in source
    assert "require_process_tree_containment=True" in source

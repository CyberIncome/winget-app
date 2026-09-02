"""Source contracts for final interactive workbench behavior."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_entrypoints_use_workbench_window():
    main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    smoke_source = (ROOT / "scripts" / "smoke_gui.py").read_text(encoding="utf-8")
    assert "from src.ui.workbench_window import WorkbenchMainWindow" in main_source
    assert "window = WorkbenchMainWindow()" in main_source
    assert "from src.ui.workbench_window import WorkbenchMainWindow" in smoke_source
    assert "window = WorkbenchMainWindow()" in smoke_source


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


def test_workers_validate_export_and_bound_show_output():
    source = (ROOT / "src" / "logic" / "worker_jobs.py").read_text(
        encoding="utf-8"
    )
    assert "package_show_worker" in source
    assert "result.stdout[:256 * 1024]" in source
    assert "winget_export_worker" in source
    assert "json.loads" in source
    assert "16 * 1024 * 1024" in source
    assert "created no file" in source

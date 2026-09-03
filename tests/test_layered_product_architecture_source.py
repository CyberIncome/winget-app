"""Durable source contracts for the additive product GUI stack."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_final_entrypoint_uses_integrity_window_and_gui_polish():
    main_source = _source("src/main.py")
    smoke_source = _source("scripts/smoke_gui.py")
    expected_import = "UpdateProgressMainWindow"
    layout_import = "from src.ui.layout_polish import apply_layout_polish"
    context_import = "from src.ui.context_polish import apply_context_polish"
    selection_import = "from src.ui.selection_polish import apply_selection_polish"
    for source in (main_source, smoke_source):
        assert expected_import in source
        assert "window = UpdateProgressMainWindow()" in source
        assert layout_import in source
        assert context_import in source
        assert selection_import in source
        assert "apply_layout_polish(window)" in source
        assert "apply_context_polish(window)" in source
        assert "apply_update_progress(window)" in source
        assert "apply_selection_polish(window)" in source


def test_product_layers_remain_in_order():
    progress = _source("src/ui/update_progress.py")
    startup = _source("src/ui/startup_optimized_window.py")
    integrity = _source("src/ui/version_integrity_window.py")
    version_aware = _source("src/ui/version_aware_window.py")
    workbench = _source("src/ui/workbench_window.py")
    product = _source("src/ui/product_window.py")
    experience = _source("src/ui/experience_window.py")

    assert "class UpdateProgressMainWindow(StartupOptimizedMainWindow)" in progress
    assert "class StartupOptimizedMainWindow(VersionIntegrityMainWindow)" in startup
    assert "class VersionIntegrityMainWindow(VersionAwareMainWindow)" in integrity
    assert "class VersionAwareMainWindow(WorkbenchMainWindow)" in version_aware
    assert "class WorkbenchMainWindow(ProductMainWindow)" in workbench
    assert "class ProductMainWindow(ExperienceMainWindow)" in product
    assert "class ExperienceMainWindow(RuntimeMainWindow)" in experience


def test_layout_polish_is_geometry_only_not_package_execution_logic():
    source = _source("src/ui/layout_polish.py")
    assert "apply_layout_polish" in source
    assert "QScrollArea" in source
    assert "QBoxLayout.Direction.TopToBottom" in source
    assert "update_splitter.setSizes" in source
    assert "inventory_splitter.setSizes" in source
    assert "executor" not in source
    assert "get_update_cmd" not in source
    assert "winget" not in source.lower()


def test_context_polish_is_presentation_only():
    source = _source("src/ui/context_polish.py")
    assert "apply_context_polish" in source
    assert "build_version_review_dialog" in source
    assert "update_selected_btn.setVisible" in source
    assert "search_bar.setVisible" in source
    assert "get_update_cmd" not in source
    assert "executor" not in source
    assert "batch_update(" not in source


def test_selection_polish_owns_unified_row_checkbox_action_dispatch():
    source = _source("src/ui/selection_polish.py")
    assert "apply_selection_polish" in source
    assert "ExtendedSelection" in source
    assert "ShiftModifier" in source
    assert "ControlModifier" in source
    assert "Select Visible" in source
    assert "Clear Selection" in source
    assert "Update Selected" in source
    assert "window.batch_update(refs)" in source
    # Selection policy may dispatch already-proven refs, but it must never build
    # or execute package commands itself.
    assert "get_update_cmd" not in source
    assert "executor" not in source
    assert "QProcess" not in source


def test_update_progress_never_rewires_core_qprocess_signals():
    source = _source("src/ui/update_progress.py")
    assert "process.finished.disconnect" not in source
    assert "process.finished.connect" not in source
    assert "window.process_finished =" not in source
    assert "window._handle_process_output =" not in source
    assert "window.run_next_update =" not in source


def test_startup_inventory_is_split_into_fast_base_and_slow_enrichment():
    source = _source("src/ui/startup_optimized_window.py")
    workers = _source("src/logic/worker_jobs.py")
    inventory = _source("src/logic/inventory_scan.py")

    assert "inventory_base_scan_worker" in source
    assert "portable_inventory_worker" in source
    assert "inventoryLoadingProgress" in source
    assert "def inventory_base_scan_worker" in workers
    assert "def portable_inventory_worker" in workers
    assert "def collect_registry_inventory" in inventory
    assert "def collect_portable_inventory" in inventory

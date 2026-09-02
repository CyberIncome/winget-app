"""Durable source contracts for the additive product GUI stack."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_final_entrypoint_uses_integrity_window_and_gui_polish():
    main_source = _source("src/main.py")
    smoke_source = _source("scripts/smoke_gui.py")
    expected_import = (
        "from src.ui.startup_optimized_window import StartupOptimizedMainWindow"
    )
    layout_import = "from src.ui.layout_polish import apply_layout_polish"
    context_import = "from src.ui.context_polish import apply_context_polish"
    selection_import = "from src.ui.selection_polish import apply_selection_polish"
    for source in (main_source, smoke_source):
        assert expected_import in source
        assert "window = StartupOptimizedMainWindow()" in source
        assert layout_import in source
        assert context_import in source
        assert selection_import in source
        assert "apply_layout_polish(window)" in source
        assert "apply_context_polish(window)" in source
        assert "apply_selection_polish(window)" in source


def test_product_layers_remain_in_order():
    startup = _source("src/ui/startup_optimized_window.py")
    integrity = _source("src/ui/version_integrity_window.py")
    version_aware = _source("src/ui/version_aware_window.py")
    workbench = _source("src/ui/workbench_window.py")
    product = _source("src/ui/product_window.py")
    experience = _source("src/ui/experience_window.py")

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


def test_selection_polish_is_interaction_only():
    source = _source("src/ui/selection_polish.py")
    assert "apply_selection_polish" in source
    assert "Check Visible" in source
    assert "Clear Checked" in source
    assert "get_update_cmd" not in source
    assert "executor" not in source
    assert "batch_update(" not in source

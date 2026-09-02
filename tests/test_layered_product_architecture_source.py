"""Durable source contracts for the additive product GUI stack."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_final_entrypoint_uses_integrity_window_and_layout_polish():
    main_source = _source("src/main.py")
    smoke_source = _source("scripts/smoke_gui.py")
    expected_import = (
        "from src.ui.version_integrity_window import VersionIntegrityMainWindow"
    )
    polish_import = "from src.ui.layout_polish import apply_layout_polish"
    assert expected_import in main_source
    assert "window = VersionIntegrityMainWindow()" in main_source
    assert polish_import in main_source
    assert "apply_layout_polish(window)" in main_source
    assert expected_import in smoke_source
    assert "window = VersionIntegrityMainWindow()" in smoke_source
    assert polish_import in smoke_source
    assert "apply_layout_polish(window)" in smoke_source


def test_product_layers_remain_in_order():
    integrity = _source("src/ui/version_integrity_window.py")
    version_aware = _source("src/ui/version_aware_window.py")
    workbench = _source("src/ui/workbench_window.py")
    product = _source("src/ui/product_window.py")
    experience = _source("src/ui/experience_window.py")

    assert "class VersionIntegrityMainWindow(VersionAwareMainWindow)" in integrity
    assert "class VersionAwareMainWindow(WorkbenchMainWindow)" in version_aware
    assert "class WorkbenchMainWindow(ProductMainWindow)" in workbench
    assert "class ProductMainWindow(ExperienceMainWindow)" in product
    assert "class ExperienceMainWindow(RuntimeMainWindow)" in experience


def test_layout_polish_is_geometry_only_not_package_execution_logic():
    source = _source("src/ui/layout_polish.py")
    assert "apply_layout_polish" in source
    assert "QScrollArea" in source
    assert "QBoxLayout.TopToBottom" in source
    assert "update_splitter.setSizes" in source
    assert "inventory_splitter.setSizes" in source
    assert "executor" not in source
    assert "get_update_cmd" not in source
    assert "winget" not in source.lower()

"""Durable source contracts for the additive product GUI stack."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_final_entrypoint_uses_integrity_window():
    main_source = _source("src/main.py")
    smoke_source = _source("scripts/smoke_gui.py")
    expected_import = (
        "from src.ui.version_integrity_window import VersionIntegrityMainWindow"
    )
    assert expected_import in main_source
    assert "window = VersionIntegrityMainWindow()" in main_source
    assert expected_import in smoke_source
    assert "window = VersionIntegrityMainWindow()" in smoke_source


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

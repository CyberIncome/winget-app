"""Source-level product experience contracts that do not require Qt execution."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_and_smoke_route_through_product_window():
    main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    smoke_source = (ROOT / "scripts" / "smoke_gui.py").read_text(encoding="utf-8")
    assert "from src.ui.product_window import ProductMainWindow" in main_source
    assert "window = ProductMainWindow()" in main_source
    assert "from src.ui.product_window import ProductMainWindow" in smoke_source
    assert "window = ProductMainWindow()" in smoke_source


def test_product_layer_adds_bounded_history_above_experience_layer():
    source = (ROOT / "src" / "ui" / "product_window.py").read_text(
        encoding="utf-8"
    )
    assert "class ProductMainWindow(ExperienceMainWindow)" in source
    assert 'self.sidebar.addItem("History")' in source
    assert "record_event" in source
    assert "load_history" in source
    assert "clear_history" in source
    assert "export_dashboard_snapshot" in source
    assert "QFileDialog.getSaveFileName" in source
    assert 'if "pytest" in sys.modules' in source


def test_experience_layer_preserves_runtime_boundary_and_managed_workers():
    source = (ROOT / "src" / "ui" / "experience_window.py").read_text(
        encoding="utf-8"
    )
    assert "class ExperienceMainWindow(RuntimeMainWindow)" in source
    assert '"app-release"' in source
    assert "app_release_worker" in source
    assert '"diagnostics"' in source
    assert "diagnostics_worker" in source
    assert "filter_ignored_updates" in source
    assert "BatchResultTracker" in source
    assert "QMessageBox.question" in source
    assert "QProcess.FailedToStart" in source


def test_product_settings_expose_user_controls():
    source = (ROOT / "src" / "ui" / "experience_window.py").read_text(
        encoding="utf-8"
    )
    assert "Automatically check for new dashboard releases" in source
    assert "Confirm before starting package updates" in source
    assert "Run remote-version detective after inventory scans" in source
    assert "Restore Ignored Updates" in source
    assert "Copy Diagnostics" in source

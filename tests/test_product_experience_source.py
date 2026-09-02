"""Source-level product experience contracts that do not require Qt execution."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_routes_through_experience_window():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert "from src.ui.experience_window import ExperienceMainWindow" in source
    assert "window = ExperienceMainWindow()" in source


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

"""Regression coverage for the foreground Winget update progress surface."""

from collections import deque
from pathlib import Path

from src.ui.update_progress import (
    UpdateProgressMainWindow,
    _observe_output,
    _start_package_ui,
    apply_update_progress,
    observe_winget_update_output,
)


ROOT = Path(__file__).resolve().parents[1]


def test_byte_progress_is_converted_to_real_percentage():
    observation = observe_winget_update_output(
        "Downloading\r  76.8 MB / 153.6 MB"
    )

    assert observation is not None
    assert observation.stage == "Downloading"
    assert observation.percent == 50
    assert observation.detail == "76.8 MB / 153.6 MB"


def test_literal_percentage_is_used_when_winget_reports_one():
    observation = observe_winget_update_output("Installing 73%")

    assert observation is not None
    assert observation.stage == "Installing"
    assert observation.percent == 73


def test_opaque_installer_stage_never_invents_percentage():
    observation = observe_winget_update_output(
        "Successfully verified installer hash\r\nStarting package install..."
    )

    assert observation is not None
    assert observation.stage == "Installing"
    assert observation.percent is None
    assert "no percentage" in observation.detail.lower()


def test_latest_stage_wins_when_one_chunk_contains_download_and_install():
    observation = observe_winget_update_output(
        "100 MB / 100 MB\r\n"
        "Successfully verified installer hash\r\n"
        "Starting package install...\r\n"
    )

    assert observation is not None
    assert observation.stage == "Installing"
    assert observation.percent is None
    assert "no percentage" in observation.detail.lower()


def test_no_applicable_upgrade_is_not_misclassified_as_resolving():
    observation = observe_winget_update_output("No applicable upgrade found.")

    assert observation is not None
    assert observation.stage == "Finishing"
    assert observation.percent is None


def _window(qtbot):
    window = UpdateProgressMainWindow()
    qtbot.addWidget(window)
    apply_update_progress(window)
    return window


def test_progress_surface_shows_package_stage_and_real_download_percent(qtbot):
    window = _window(qtbot)
    window.apply_winget_results(
        [
            {
                "Name": "Blender",
                "Id": "BlenderFoundation.Blender",
                "Version": "5.2.0",
                "Available": "5.2.1",
                "Source": "winget",
            }
        ]
    )

    window.current_operation = "update"
    window.current_package_ref = {
        "value": "BlenderFoundation.Blender",
        "match_by": "id",
        "source": "winget",
        "version": "5.2.1",
        "silent": True,
    }
    window._queue_total = 1
    window.process_queue = deque()

    _start_package_ui(window)
    # The parent window is not shown in this unit test; visibility intent is
    # represented by the widget's hidden state rather than isVisible().
    assert window.update_progress_banner.isHidden() is False
    assert window.update_progress_title.text() == "Updating Blender"
    assert window.update_progress_meta.text() == "Package 1 of 1"
    assert window.update_operation_progress.minimum() == 0
    assert window.update_operation_progress.maximum() == 0
    assert "elapsed" in window.update_progress_detail.text().lower()

    _observe_output(window, "  25 MB / 100 MB")
    assert window.update_operation_progress.maximum() == 100
    assert window.update_operation_progress.value() == 25
    assert "25 MB / 100 MB" in window.update_progress_detail.text()

    _observe_output(window, "Starting package install...")
    assert window.update_operation_progress.minimum() == 0
    assert window.update_operation_progress.maximum() == 0
    assert "no percentage" in window.update_progress_detail.text().lower()

    window.current_operation = None
    window._update_progress_timer.stop()


def test_refresh_output_does_not_activate_update_progress_surface(qtbot):
    window = _window(qtbot)
    window.current_operation = "refresh"

    window._handle_process_output("stdout", "Installing 73%\n")

    assert window.update_progress_banner.isHidden() is True
    assert window.update_operation_progress.minimum() == 0
    assert window.update_operation_progress.maximum() == 0


def test_apply_update_progress_is_idempotent(qtbot):
    window = UpdateProgressMainWindow()
    qtbot.addWidget(window)

    apply_update_progress(window)
    banner = window.update_progress_banner
    apply_update_progress(window)

    assert window.update_progress_banner is banner
    assert window._update_progress_polished is True


def test_progress_layer_never_rewires_core_qprocess_signals():
    source = (ROOT / "src" / "ui" / "update_progress.py").read_text(
        encoding="utf-8"
    )

    assert "class UpdateProgressMainWindow(StartupOptimizedMainWindow)" in source
    assert "process.finished.disconnect" not in source
    assert "process.finished.connect" not in source
    assert "window.process_finished =" not in source
    assert "window._handle_process_output =" not in source
    assert "window.run_next_update =" not in source

"""Regression tests for production QProcess protocol handling."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QProcess

from src.ui.hardened_window import HardenedMainWindow
from src.ui.production_window import ProductionMainWindow


WINGET_TABLE = """Name                           Id                           Version          Available        Source
------------------------------------------------------------------------------------------------------
Café 日本語 App                 Example.Unicode.App          1.0.0            1.1.0            winget
"""


def _make_window(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    return window


def test_refresh_parser_receives_reassembled_raw_stdout(qtbot, monkeypatch):
    window = _make_window(qtbot)
    window.current_operation = "refresh"
    window._startup_stage = "refresh"
    window.set_ui_busy("Scanning for updates...", True, "refresh")

    encoded = WINGET_TABLE.encode("utf-8")
    split = encoded.index("é".encode("utf-8")) + 1
    window._capture_refresh_stdout(encoded[:split])
    window._capture_refresh_stdout(encoded[split:])

    captured = {}

    def fake_start_job(name, target, args=(), **kwargs):
        captured["name"] = name
        captured["args"] = args
        return True

    monkeypatch.setattr(window, "_start_job", fake_start_job)
    monkeypatch.setattr(window, "handle_stdout", lambda: None)
    monkeypatch.setattr(window, "handle_stderr", lambda: None)

    window.process_finished(0, QProcess.NormalExit)

    assert captured["name"] == "winget-parse"
    assert captured["args"] == (WINGET_TABLE,)


def test_refresh_stdout_overflow_is_not_parsed_as_truncated_table(
    qtbot, monkeypatch
):
    window = _make_window(qtbot)
    window.current_operation = "refresh"
    window._startup_stage = "refresh"
    window.set_ui_busy("Scanning for updates...", True, "refresh")
    window._max_output_bytes = 16

    window._capture_refresh_stdout(b"Name Id Version Available")

    assert window._process_stdout_invalid_reason is not None
    assert "exceeded" in window._process_stdout_invalid_reason
    assert len(window._process_stdout_bytes) == 16

    captured = {}

    def fake_start_job(name, target, args=(), **kwargs):
        captured["name"] = name
        captured["args"] = args
        return True

    monkeypatch.setattr(window, "_start_job", fake_start_job)
    monkeypatch.setattr(window, "handle_stdout", lambda: None)
    monkeypatch.setattr(window, "handle_stderr", lambda: None)

    window.process_finished(0, QProcess.NormalExit)

    assert captured["name"] == "winget-parse"
    assert captured["args"] == ("",)
    assert "output is invalid" in window.console.toPlainText()


def test_refresh_stdout_read_failure_invalidates_scan(qtbot):
    window = _make_window(qtbot)
    window.current_operation = "refresh"
    window._process_stdout_bytes.extend(b"partial table")

    class BrokenProcess:
        def readAllStandardOutput(self):
            raise RuntimeError("stdout handle raced")

    original_process = window.process
    window.process = BrokenProcess()
    try:
        window.handle_stdout()
    finally:
        window.process = original_process

    assert window._process_stdout_invalid_reason is not None
    assert "stdout handling failed" in window._process_stdout_invalid_reason
    assert "stdout handle raced" in window._process_stdout_invalid_reason


def test_finished_callback_exception_aborts_update_and_restores_idle(
    qtbot, monkeypatch
):
    window = _make_window(qtbot)
    window.current_operation = "update"
    window.set_ui_busy("Updating apps...", True, "update")
    window.process_queue = deque(
        [{"value": "Second.Package", "match_by": "id", "silent": True}]
    )

    monkeypatch.setattr(window, "handle_stdout", lambda: None)
    monkeypatch.setattr(window, "handle_stderr", lambda: None)

    def broken_finished(self, code, status):
        raise RuntimeError("completion exploded")

    monkeypatch.setattr(HardenedMainWindow, "process_finished", broken_finished)

    window.process_finished(1, QProcess.NormalExit)

    assert window.current_operation is None
    assert list(window.process_queue) == []
    assert "update" not in window._active_tasks
    assert window.update_selected_btn.isEnabled()


def test_error_callback_exception_restores_refresh_and_advances_startup(
    qtbot, monkeypatch
):
    window = _make_window(qtbot)
    window.current_operation = "refresh"
    window._startup_stage = "refresh"
    window.set_ui_busy("Scanning for updates...", True, "refresh")
    advanced = []

    monkeypatch.setattr(
        window,
        "_advance_startup_after_refresh",
        lambda: advanced.append(True),
    )

    def broken_error(self, error):
        raise RuntimeError("error handler exploded")

    monkeypatch.setattr(HardenedMainWindow, "handle_process_error", broken_error)

    window.handle_process_error(QProcess.UnknownError)

    assert window.current_operation is None
    assert "refresh" not in window._active_tasks
    assert advanced == [True]

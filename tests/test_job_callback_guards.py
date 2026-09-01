"""Regression tests for managed-job callback exception containment."""

from __future__ import annotations

from src.ui.production_window import ProductionMainWindow


def test_success_handler_exception_routes_to_failure_recovery(
    qtbot, monkeypatch
):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.current_operation = "refresh"
    window.set_ui_busy("Scanning for updates...", True, "refresh")
    advanced = []
    monkeypatch.setattr(
        window,
        "_advance_startup_after_refresh",
        lambda: advanced.append(True),
    )

    def broken_success(_value):
        raise RuntimeError("result application exploded")

    window._dispatch_job_success(
        "winget-parse",
        [],
        broken_success,
        window._winget_parse_failed,
    )

    assert window.current_operation is None
    assert "refresh" not in window._active_tasks
    assert advanced == [True]
    assert "result handling failed" in window.console.toPlainText()


def test_failure_recovery_exception_is_contained(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)

    def broken_recovery(_message):
        raise RuntimeError("recovery exploded")

    window._handle_job_failure(
        "synthetic-job",
        "synthetic failure",
        broken_recovery,
    )

    console = window.console.toPlainText()
    assert "synthetic failure" in console
    assert "Failure recovery for synthetic-job also failed" in console

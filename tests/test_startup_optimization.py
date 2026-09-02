"""Regression tests for the parallel, non-blocking startup orchestration."""

from src.ui.startup_optimized_window import StartupOptimizedMainWindow


def _window(qtbot):
    window = StartupOptimizedMainWindow()
    qtbot.addWidget(window)
    return window


def _dummy_worker(_queue):
    return None


def test_detective_is_deferred_until_parallel_base_is_ready(qtbot):
    window = _window(qtbot)
    window._startup_stage = "parallel-base"

    assert window._start_job("detective", _dummy_worker, timeout=17) is True
    assert "detective" not in window._managed_jobs
    assert window._deferred_startup_detective is not None
    assert window._deferred_startup_detective["timeout"] == 17


def test_base_ready_requires_both_authoritative_scans(qtbot, monkeypatch):
    window = _window(qtbot)
    window._startup_stage = "parallel-base"
    scheduled = []
    monkeypatch.setattr(
        "src.ui.startup_optimized_window.QTimer.singleShot",
        lambda _delay, callback: scheduled.append(callback),
    )

    window._startup_refresh_done = True
    window._finish_startup_base_if_ready()
    assert window._startup_stage == "parallel-base"
    assert scheduled == []

    window._startup_inventory_done = True
    window._finish_startup_base_if_ready()
    assert window._startup_stage == "ready"
    assert scheduled == [window._start_post_ready_enrichment]


def test_startup_detective_does_not_hold_global_busy_state(qtbot):
    window = _window(qtbot)
    window._startup_stage = "parallel-base"

    before = set(window._active_tasks)
    window.set_ui_busy("Detective: Checking for updates...", True, "detective")
    assert window._active_tasks == before


def test_app_release_check_is_deferred_during_parallel_base(qtbot):
    window = _window(qtbot)
    window._startup_stage = "parallel-base"

    window.check_app_release()
    assert window._startup_app_release_deferred is True
    assert "app-release" not in window._managed_jobs


def test_inventory_refresh_is_blocked_while_detective_owns_snapshot(qtbot):
    window = _window(qtbot)
    window._startup_stage = "ready"
    sentinel = object()
    window._managed_jobs["detective"] = sentinel

    window.refresh_inventory()

    assert window._managed_jobs["detective"] is sentinel
    assert "Detective" in window.status_label.text()
    assert "inventory" not in window._active_tasks
    window._managed_jobs.pop("detective")

"""Regression tests for the parallel, non-blocking startup orchestration."""

from src.logic.worker_jobs import (
    inventory_base_scan_worker,
    portable_inventory_worker,
)
from src.ui.main_window import UpdateModel
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


def test_base_ready_requires_update_and_fast_inventory_base(qtbot, monkeypatch):
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


def test_startup_inventory_uses_fast_registry_base_worker(qtbot, monkeypatch):
    window = _window(qtbot)
    window._startup_stage = "parallel-base"
    captured = {}

    def fake_start_job(name, target, **kwargs):
        captured["name"] = name
        captured["target"] = target
        captured["kwargs"] = kwargs
        return True

    monkeypatch.setattr(window, "_start_job", fake_start_job)
    before = set(window._active_tasks)

    window._start_startup_inventory_scan()

    assert captured["name"] == "inventory"
    assert captured["target"] is inventory_base_scan_worker
    assert captured["kwargs"]["timeout"] == 90
    assert window._active_tasks == before


def test_inventory_has_local_loading_state_independent_of_global_bar(qtbot):
    window = _window(qtbot)
    window._set_inventory_loading("Discovering shortcut apps...", True)

    assert window.inventory_loading_banner.isVisible() is False  # parent not shown
    assert window.inventory_loading_label.text() == "Discovering shortcut apps..."
    assert window.inventory_loading_progress.minimum() == 0
    assert window.inventory_loading_progress.maximum() == 0
    assert window.inventory_loading_progress.isHidden() is False


def test_inventory_base_profile_is_logged_applied_and_schedules_shortcuts(qtbot, monkeypatch):
    window = _window(qtbot)
    window._startup_stage = "parallel-base"
    window._startup_refresh_done = True
    messages = []
    scheduled = []
    monkeypatch.setattr(window.logger, "info", lambda *args: messages.append(args))
    monkeypatch.setattr(window, "set_inventory_model", lambda data: messages.append(("model", data)))
    monkeypatch.setattr(window, "_finish_startup_base_if_ready", lambda: None)
    monkeypatch.setattr(
        "src.ui.startup_optimized_window.QTimer.singleShot",
        lambda _delay, callback: scheduled.append(callback),
    )

    window._inventory_job_succeeded(
        {
            "registry": [{"name": "One"}],
            "inventory": [{"Name": "One"}],
            "timings": {
                "registry_seconds": 0.1,
                "assembly_seconds": 0.02,
                "worker_total_seconds": 0.12,
                "registry_items": 1,
                "inventory_items": 1,
            },
        }
    )

    assert window._startup_inventory_done is True
    assert window._cached_reg_data == [{"name": "One"}]
    assert any(message and message[0] == "model" for message in messages)
    assert any(
        message and isinstance(message[0], str) and "STARTUP INVENTORY BASE PROFILE" in message[0]
        for message in messages
    )
    assert window._start_portable_inventory_scan in scheduled


def test_portable_inventory_worker_is_background_enrichment(qtbot, monkeypatch):
    window = _window(qtbot)
    model = UpdateModel(
        [{"Name": "Installed", "Id": "Installed.App"}],
        is_inventory=True,
    )
    window.inventory_proxy.setSourceModel(model)
    captured = {}

    def fake_start_job(name, target, **kwargs):
        captured["name"] = name
        captured["target"] = target
        captured["kwargs"] = kwargs
        return True

    monkeypatch.setattr(window, "_start_job", fake_start_job)
    window._start_portable_inventory_scan()

    assert captured["name"] == "inventory-portable"
    assert captured["target"] is portable_inventory_worker
    assert captured["kwargs"]["args"] == (["Installed"],)
    assert captured["kwargs"]["timeout"] == 180
    assert "shortcut" in window.inventory_loading_label.text().lower()


def test_portable_inventory_appends_without_reindexing_base_rows(qtbot):
    window = _window(qtbot)
    model = UpdateModel(
        [
            {"Name": "Alpha", "Id": "Alpha.App"},
            {"Name": "Zulu", "Id": "Zulu.App"},
        ],
        is_inventory=True,
    )
    window.inventory_proxy.setSourceModel(model)

    window._portable_inventory_succeeded(
        {
            "inventory": [
                {"Name": "Beta Portable", "Id": "Portable.Beta", "Type": "Portable"}
            ],
            "timings": {"total_seconds": 3.0, "portable_candidates": 1},
        }
    )

    assert [item["Name"] for item in model._data] == [
        "Alpha",
        "Zulu",
        "Beta Portable",
    ]
    assert model._selected["Portable.Beta"] is False
    assert window._stat_installed == 3


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

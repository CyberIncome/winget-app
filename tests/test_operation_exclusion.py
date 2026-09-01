"""Regression tests for foreground operation exclusion."""

from __future__ import annotations

from src.ui.production_window import ProductionMainWindow


def test_update_request_is_blocked_while_inventory_task_is_active(
    qtbot, monkeypatch
):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.set_ui_busy("Scanning system inventory...", True, "inventory")

    started = []
    monkeypatch.setattr(
        window.process,
        "start",
        lambda *_args, **_kwargs: started.append(True),
    )

    window.batch_update(
        [{"value": "Example.App", "match_by": "id", "source": "winget"}]
    )

    assert started == []
    assert window.current_operation is None
    assert window._active_tasks == {"inventory"}
    assert "update request ignored" in window.console.toPlainText()


def test_refresh_updates_is_blocked_while_inventory_task_is_active(
    qtbot, monkeypatch
):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.set_ui_busy("Scanning system inventory...", True, "inventory")

    started = []
    monkeypatch.setattr(
        window.process,
        "start",
        lambda *_args, **_kwargs: started.append(True),
    )

    window.refresh_updates()

    assert started == []
    assert window.current_operation is None
    assert window._active_tasks == {"inventory"}


def test_refresh_inventory_is_blocked_while_update_task_is_active(
    qtbot, monkeypatch
):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.current_operation = "update"
    window.set_ui_busy("Updating apps...", True, "update")

    started_jobs = []
    monkeypatch.setattr(
        window,
        "_start_job",
        lambda *args, **kwargs: started_jobs.append((args, kwargs)) or True,
    )

    window.refresh_inventory()

    assert started_jobs == []
    assert "inventory" not in window._managed_jobs
    assert window._active_tasks == {"update"}


def test_update_selected_double_click_path_cannot_bypass_busy_state(
    qtbot, monkeypatch
):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results(
        [
            {
                "Name": "Example App",
                "Id": "Example.App",
                "Version": "1.0",
                "Available": "2.0",
                "Source": "winget",
            }
        ]
    )
    model = window.proxy_model.sourceModel()
    model.set_checked(0, True)
    window.set_ui_busy("Scanning system inventory...", True, "inventory")

    started = []
    monkeypatch.setattr(
        window.process,
        "start",
        lambda *_args, **_kwargs: started.append(True),
    )

    # update_selected is the method wired to table double-click in the
    # historical presentation layer. The controller gate must still win.
    window.update_selected()

    assert started == []
    assert "update" not in window._active_tasks
    assert window._active_tasks == {"inventory"}

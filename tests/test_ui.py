import pytest
from collections import deque
from PySide6.QtWidgets import QTableView, QPlainTextEdit, QPushButton
from PySide6.QtCore import QProcess, Qt
from src.ui.main_window import MainWindow, UpdateModel

def test_main_window_components(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    
    # Check for core components
    assert isinstance(window.table, QTableView)
    assert isinstance(window.console, QPlainTextEdit)
    assert window.console.objectName() == "console"
    
    # Check for buttons
    assert isinstance(window.refresh_btn, QPushButton)
    assert isinstance(window.update_selected_btn, QPushButton)
    assert isinstance(window.update_all_btn, QPushButton)
    assert window.update_all_btn.objectName() == "updateAll"

def test_selection_logic():
    # Test data
    data = [
        {"Name": "App1", "Id": "Id1", "Version": "1.0", "Available": "1.1", "Source": "winget"},
        {"Name": "App2", "Id": "Id2", "Version": "2.0", "Available": "2.1", "Source": "winget"},
    ]
    model = UpdateModel(data)
    
    # Check initial state (column 0 is checkboxes)
    assert model.data(model.index(0, 0), Qt.CheckStateRole) == Qt.Unchecked
    
    # Toggle selection
    model.setData(model.index(0, 0), Qt.Checked, Qt.CheckStateRole)
    assert model.data(model.index(0, 0), Qt.CheckStateRole) == Qt.Checked
    
    # Get selected IDs
    selected = model.get_selected_ids()
    assert selected == ["Id1"]


def test_selection_uses_name_when_winget_id_is_truncated():
    data = [
        {
            "Name": "Visual Studio Build Tools 2022",
            "Id": "Microsoft.VisualStudio.2022.BuildToo\u2026",
            "Version": "17.14.27",
            "Available": "17.14.28",
        },
    ]
    model = UpdateModel(data)

    model.setData(model.index(0, 0), Qt.Checked, Qt.CheckStateRole)

    assert model.get_selected_packages() == [
        {
            "value": "Visual Studio Build Tools 2022",
            "match_by": "name",
        }
    ]


def test_selection_prefers_valid_winget_id():
    data = [
        {
            "Name": "Google Chrome",
            "Id": "Google.Chrome",
            "Version": "120.0",
            "Available": "121.0",
        },
    ]
    model = UpdateModel(data)

    model.setData(model.index(0, 0), Qt.Checked, Qt.CheckStateRole)

    assert model.get_selected_packages() == [
        {"value": "Google.Chrome", "match_by": "id"}
    ]


def test_table_row_selection_checks_checkbox(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results([
        {
            "Name": "Google Chrome",
            "Id": "Google.Chrome",
            "Version": "120.0",
            "Available": "121.0",
        },
    ])
    model = window.proxy_model.sourceModel()

    window.table.selectRow(0)

    assert model.data(model.index(0, 0), Qt.CheckStateRole) == Qt.Checked


def test_checkbox_selection_highlights_row(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results([
        {
            "Name": "Google Chrome",
            "Id": "Google.Chrome",
            "Version": "120.0",
            "Available": "121.0",
        },
    ])
    model = window.proxy_model.sourceModel()

    model.setData(model.index(0, 0), Qt.Checked, Qt.CheckStateRole)

    selected_rows = window.table.selectionModel().selectedRows()
    assert [index.row() for index in selected_rows] == [0]


def test_winget_progress_output_replaces_live_console_line(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.current_operation = "update"
    window.set_ui_busy("Updating apps...", True, "update")
    window._handle_process_output("stdout", "|\r")
    window._handle_process_output("stdout", "/\r")
    window._handle_process_output("stdout", "Installing 10%\r")
    window._handle_process_output("stdout", "Installing 20%\r")

    assert window.console.toPlainText() == "Installing 20%"
    assert window.progress_bar.maximum() == 100
    assert window.progress_bar.value() == 20


def test_update_spinner_keeps_progress_bar_animating(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.current_operation = "update"
    window.set_ui_busy("Updating apps...", True, "update")
    window._handle_process_output("stdout", "|\r")
    window._handle_process_output("stdout", "/\r")

    assert window.progress_bar.minimum() == 0
    assert window.progress_bar.maximum() == 0


def test_console_output_is_not_duplicated_by_logging_bridge(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._append_console_line("Sample console line")

    assert window.console.toPlainText() == "Sample console line"

def test_main_window_title(qtbot):
    window = MainWindow()
    assert window.windowTitle() == "Winget Universal Dashboard"


def test_process_error_clears_refresh_busy_state(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_ui_busy("Scanning for updates...", True, "refresh")
    window.current_operation = "refresh"

    window.handle_process_error(QProcess.FailedToStart)

    assert "refresh" not in window._active_tasks
    assert window.current_operation is None
    assert window.refresh_btn.isEnabled()


def test_process_finished_retries_without_silent(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_operation = "update"
    window.current_package_ref = {
        "value": "Perplexity.Comet",
        "match_by": "id",
        "silent": True,
    }
    window.process_queue = deque()

    window.process_finished(-1, QProcess.CrashExit)

    assert window.process_queue[0]["silent"] is False
    assert (
        window.process_queue[0]["retried_without_silent"]
        is True
    )

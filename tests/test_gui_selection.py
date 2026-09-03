"""Regression tests for independent, reliable checkbox selection behavior."""

from types import SimpleNamespace

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QTableView

from src.ui.main_window import CustomSortProxy, UpdateModel
from src.ui.selection_polish import (
    _CheckboxColumnFilter,
    apply_selection_polish,
    clear_all_checked,
    set_visible_checked,
    update_checked,
)
from src.ui.version_integrity_window import VersionIntegrityMainWindow


def _window(qtbot):
    window = VersionIntegrityMainWindow()
    qtbot.addWidget(window)
    apply_selection_polish(window)
    window.apply_winget_results(
        [
            {
                "Name": "Alpha",
                "Id": "Example.Alpha",
                "Version": "1.0",
                "Available": "2.0",
                "Source": "winget",
            },
            {
                "Name": "Beta",
                "Id": "Example.Beta",
                "Version": "1.0",
                "Available": "2.0",
                "Source": "winget",
            },
        ]
    )
    return window


def _checked(model, row):
    return (
        model.data(model.index(row, 0), Qt.ItemDataRole.CheckStateRole)
        == Qt.CheckState.Checked
    )


def test_row_highlight_is_single_selection_and_does_not_change_checkboxes(qtbot):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()
    assert model is not None
    assert window.table.selectionMode() == QTableView.SelectionMode.SingleSelection

    assert model.set_checked(0, True) is True
    window.table.selectRow(1)

    assert _checked(model, 0) is True
    assert _checked(model, 1) is False
    assert [index.row() for index in window.table.selectionModel().selectedRows()] == [1]


def test_keyboard_native_checkbox_toggle_does_not_move_inspection_highlight(qtbot):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()
    assert model is not None

    window.table.selectRow(1)
    model.set_checked(0, True, emit_signal=True)

    assert _checked(model, 0) is True
    assert [index.row() for index in window.table.selectionModel().selectedRows()] == [1]


def test_highlight_only_is_never_an_update_target(qtbot, monkeypatch):
    window = _window(qtbot)
    captured = []
    monkeypatch.setattr(window, "batch_update", lambda refs: captured.extend(refs))

    window.table.selectRow(0)
    update_checked(window)

    assert captured == []
    assert "Check one or more" in window.status_label.text()


def test_checked_row_is_the_only_update_target(qtbot, monkeypatch):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()
    captured = []
    monkeypatch.setattr(window, "batch_update", lambda refs: captured.extend(refs))

    # Inspect Beta while explicitly checking Alpha. The action must follow the
    # checkbox, not the highlighted row.
    window.table.selectRow(1)
    model.set_checked(0, True)
    update_checked(window)

    assert len(captured) == 1
    assert captured[0]["value"] == "Example.Alpha"
    assert captured[0]["match_by"] == "id"
    assert captured[0]["source"] == "winget"
    assert captured[0]["version"] == "2.0"


def test_visible_bulk_check_respects_filter_and_clear_is_independent(qtbot):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()
    assert model is not None

    window.search_bar.setText("Alpha")
    assert set_visible_checked(window, True) == 1
    assert _checked(model, 0) is True
    assert _checked(model, 1) is False

    window.table.selectRow(0)
    assert clear_all_checked(window) == 1
    assert _checked(model, 0) is False
    assert window.table.selectionModel().hasSelection() is True


def test_selection_polish_restores_full_width_after_model_reload(qtbot):
    window = _window(qtbot)

    update_model = UpdateModel(
        [{"Name": "Gamma", "Id": "Example.Gamma"}],
    )
    inventory_model = UpdateModel(
        [{"Name": "Gamma", "Id": "Example.Gamma"}],
        is_inventory=True,
    )
    window.proxy_model.setSourceModel(update_model)
    window.inventory_proxy.setSourceModel(inventory_model)
    window.table.setColumnWidth(0, 40)
    window.inventory_table.setColumnWidth(0, 40)
    QApplication.processEvents()

    assert window.table.columnWidth(0) >= 52
    assert window.inventory_table.columnWidth(0) >= 52
    assert window.check_visible_btn.text() == "Check Visible"
    assert window.clear_checked_btn.text() == "Clear Checked"
    assert window.update_selected_btn.text() == "Update Checked"


def test_checkbox_filter_is_safe_during_qt_object_teardown(qapp):
    table = QTableView()
    proxy = CustomSortProxy()
    table.setModel(proxy)
    window = SimpleNamespace(table=table)
    event_filter = _CheckboxColumnFilter(window, table, proxy)
    table.viewport().installEventFilter(event_filter)

    table.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()

    assert event_filter._table is None
    assert event_filter._proxy is None
    assert event_filter._window is None

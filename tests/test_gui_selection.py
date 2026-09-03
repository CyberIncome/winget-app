"""Regression tests for unified, reliable row/checkbox selection behavior."""

from types import SimpleNamespace

from PySide6.QtCore import QEvent, QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication, QTableView

from src.ui.main_window import CustomSortProxy, UpdateModel
from src.ui.selection_polish import (
    _CheckboxColumnFilter,
    apply_selection_polish,
    clear_selection,
    select_visible,
)
from src.ui.version_integrity_window import VersionIntegrityMainWindow


def _window(qtbot, count=25):
    window = VersionIntegrityMainWindow()
    qtbot.addWidget(window)
    apply_selection_polish(window)
    window.apply_winget_results(
        [
            {
                "Name": f"Package {index + 1:02d}",
                "Id": f"Example.Package{index + 1:02d}",
                "Version": "1.0",
                "Available": "2.0",
                "Source": "winget",
            }
            for index in range(count)
        ]
    )
    window.show()
    QApplication.processEvents()
    return window


def _checked(model, row):
    return (
        model.data(model.index(row, 0), Qt.ItemDataRole.CheckStateRole)
        == Qt.CheckState.Checked
    )


def _selected_rows(window):
    return sorted(
        index.row() for index in window.table.selectionModel().selectedRows()
    )


def _click(qtbot, window, row, column=1, modifier=Qt.KeyboardModifier.NoModifier):
    index = window.proxy_model.index(row, column)
    window.table.scrollTo(index)
    QApplication.processEvents()
    rect = window.table.visualRect(index)
    assert rect.isValid()
    qtbot.mouseClick(
        window.table.viewport(),
        Qt.MouseButton.LeftButton,
        modifier=modifier,
        pos=rect.center(),
    )
    QApplication.processEvents()


def test_plain_row_click_checks_only_that_row(qtbot):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()
    assert model is not None
    assert (
        window.table.selectionMode()
        == QTableView.SelectionMode.ExtendedSelection
    )

    _click(qtbot, window, 4, column=1)
    _click(qtbot, window, 7, column=1)

    assert _selected_rows(window) == [7]
    assert _checked(model, 7) is True
    assert _checked(model, 4) is False
    assert window.update_selected_btn.text() == "Update Selected (1)"


def test_checkbox_column_uses_native_plain_and_shift_range_selection(qtbot):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()

    _click(qtbot, window, 0, column=0)
    _click(
        qtbot,
        window,
        19,
        column=0,
        modifier=Qt.KeyboardModifier.ShiftModifier,
    )

    assert _selected_rows(window) == list(range(20))
    assert all(_checked(model, row) for row in range(20))
    assert _checked(model, 20) is False
    assert window.update_selected_btn.text() == "Update Selected (20)"


def test_checkbox_column_ctrl_click_adds_and_removes_native_rows(qtbot):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()

    _click(qtbot, window, 4, column=0)
    _click(
        qtbot,
        window,
        7,
        column=0,
        modifier=Qt.KeyboardModifier.ControlModifier,
    )
    assert _selected_rows(window) == [4, 7]
    assert _checked(model, 4) is True
    assert _checked(model, 7) is True

    _click(
        qtbot,
        window,
        4,
        column=0,
        modifier=Qt.KeyboardModifier.ControlModifier,
    )
    assert _selected_rows(window) == [7]
    assert _checked(model, 4) is False
    assert _checked(model, 7) is True


def test_plain_checkbox_click_after_range_replaces_previous_selection(qtbot):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()

    _click(qtbot, window, 0, column=0)
    _click(
        qtbot,
        window,
        19,
        column=0,
        modifier=Qt.KeyboardModifier.ShiftModifier,
    )
    _click(qtbot, window, 9, column=0)

    assert _selected_rows(window) == [9]
    assert _checked(model, 9) is True
    assert sum(_checked(model, row) for row in range(25)) == 1


def test_row_body_and_checkbox_column_share_one_selection_state(qtbot):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()

    _click(qtbot, window, 2, column=1)
    assert _selected_rows(window) == [2]
    assert _checked(model, 2) is True

    _click(qtbot, window, 5, column=0)
    assert _selected_rows(window) == [5]
    assert _checked(model, 2) is False
    assert _checked(model, 5) is True


def test_selected_rows_are_update_targets(qtbot, monkeypatch):
    window = _window(qtbot, count=2)
    captured = []
    monkeypatch.setattr(window, "batch_update", lambda refs: captured.extend(refs))

    window.table.selectionModel().select(
        window.proxy_model.index(1, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    window.update_selected()

    assert len(captured) == 1
    assert captured[0]["value"] == "Example.Package02"
    assert captured[0]["match_by"] == "id"
    assert captured[0]["source"] == "winget"
    assert captured[0]["version"] == "2.0"


def test_select_visible_and_clear_selection_keep_rows_and_checks_in_sync(qtbot):
    window = _window(qtbot, count=2)
    model = window.proxy_model.sourceModel()
    assert model is not None

    window.search_bar.setText("Package 01")
    assert select_visible(window) == 1
    assert _selected_rows(window) == [0]
    assert _checked(model, 0) is True
    assert _checked(model, 1) is False

    assert clear_selection(window) == 1
    assert _selected_rows(window) == []
    assert _checked(model, 0) is False
    assert window.update_selected_btn.text() == "Update Selected"


def test_selection_polish_restores_width_and_extended_mode_after_model_reload(qtbot):
    window = _window(qtbot, count=2)

    update_model = UpdateModel([{"Name": "Gamma", "Id": "Example.Gamma"}])
    inventory_model = UpdateModel(
        [{"Name": "Gamma", "Id": "Example.Gamma"}],
        is_inventory=True,
    )
    window.proxy_model.setSourceModel(update_model)
    window.inventory_proxy.setSourceModel(inventory_model)
    window.table.setColumnWidth(0, 40)
    window.inventory_table.setColumnWidth(0, 40)
    QApplication.processEvents()

    assert (
        window.table.selectionMode()
        == QTableView.SelectionMode.ExtendedSelection
    )
    assert (
        window.inventory_table.selectionMode()
        == QTableView.SelectionMode.ExtendedSelection
    )
    assert window.table.columnWidth(0) >= 52
    assert window.inventory_table.columnWidth(0) >= 52
    assert window.check_visible_btn.text() == "Select Visible"
    assert window.clear_checked_btn.text() == "Clear Selection"
    assert window.update_selected_btn.text() == "Update Selected"


def test_checkbox_filter_is_safe_during_qt_object_teardown(qapp):
    table = QTableView()
    proxy = CustomSortProxy()
    table.setModel(proxy)
    window = SimpleNamespace(table=table)
    event_filter = _CheckboxColumnFilter(window, table)
    table.viewport().installEventFilter(event_filter)

    table.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()

    assert event_filter._table is None
    assert event_filter._window is None

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


def test_row_selection_no_longer_erases_checked_rows(qtbot):
    window = _window(qtbot)
    model = window.proxy_model.sourceModel()
    assert model is not None

    assert model.set_checked(0, True) is True
    window.table.selectRow(1)

    assert _checked(model, 0) is True
    assert _checked(model, 1) is False


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

    # Production model loaders replace each proxy source model and historically
    # resize the checkbox column back to 40 px afterward. Simulate that exact
    # ordering and confirm the queued selection-polish correction wins.
    window.proxy_model.setSourceModel(
        UpdateModel(
            [{"Name": "Gamma", "Id": "Example.Gamma"}],
        )
    )
    window.inventory_proxy.setSourceModel(
        UpdateModel(
            [{"Name": "Gamma", "Id": "Example.Gamma"}],
            is_inventory=True,
        )
    )
    window.table.setColumnWidth(0, 40)
    window.inventory_table.setColumnWidth(0, 40)
    QApplication.processEvents()

    assert window.table.columnWidth(0) >= 52
    assert window.inventory_table.columnWidth(0) >= 52
    assert window.check_visible_btn.text() == "Check Visible"
    assert window.clear_checked_btn.text() == "Clear Checked"


def test_checkbox_filter_is_safe_during_qt_object_teardown(qapp):
    # This table is deliberately *not* registered with qtbot: the test owns its
    # destruction, so pytest-qt will not later try to close a deleted wrapper.
    table = QTableView()
    proxy = CustomSortProxy()
    table.setModel(proxy)
    window = SimpleNamespace(table=table)
    event_filter = _CheckboxColumnFilter(window, table, proxy)
    table.viewport().installEventFilter(event_filter)

    table.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()

    # The destroyed signal must sever references before any late event can
    # dereference a deleted QTableView C++ object.
    assert event_filter._table is None
    assert event_filter._proxy is None
    assert event_filter._window is None

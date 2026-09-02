"""Regression tests for independent, reliable checkbox selection behavior."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from src.ui.selection_polish import (
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


def test_selection_polish_uses_full_width_checkbox_column(qtbot):
    window = _window(qtbot)

    assert window.table.columnWidth(0) >= 52
    assert window.inventory_table.columnWidth(0) >= 52
    assert window.check_visible_btn.text() == "Check Visible"
    assert window.clear_checked_btn.text() == "Clear Checked"


def test_checkbox_filter_is_safe_during_qt_object_teardown(qtbot):
    window = _window(qtbot)
    event_filter = window._checkbox_column_filters[0]

    # Force the same QObject destruction path pytest/Qt runs at interpreter
    # teardown. The filter must not dereference a deleted QTableView wrapper.
    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()

    # A late teardown event must be an inert no-op even after Qt ownership has
    # destroyed the table/viewport beneath the retained Python wrapper.
    assert event_filter.eventFilter(None, QEvent(QEvent.Type.Destroy)) is False

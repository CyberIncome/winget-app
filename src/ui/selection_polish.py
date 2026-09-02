"""Final checkbox/row-selection interaction normalization for the product UI."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QPushButton


_CHECKBOX_COLUMN_WIDTH = 52


class _CheckboxColumnFilter(QObject):
    """Make the full first-column cell a reliable checkbox hit target."""

    def __init__(self, window, table, proxy):
        super().__init__(table)
        self._window = window
        self._table = table
        self._proxy = proxy

    def _index_for_event(self, event):
        position = getattr(event, "position", None)
        if position is None:
            return None
        return self._table.indexAt(position().toPoint())

    def eventFilter(self, watched, event):
        if watched is not self._table.viewport():
            return False
        if event.type() not in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
        }:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        index = self._index_for_event(event)
        if index is None or not index.isValid() or index.column() != 0:
            return False

        # Consume both halves of the click so Qt's default item delegate cannot
        # also toggle the native indicator after our full-cell toggle.
        if event.type() == QEvent.Type.MouseButtonRelease:
            return True

        model = self._proxy.sourceModel()
        if model is None:
            return True
        source_index = self._proxy.mapToSource(index)
        row = source_index.row()
        if not 0 <= row < len(getattr(model, "_data", [])):
            return True

        checked = (
            model.data(model.index(row, 0), Qt.ItemDataRole.CheckStateRole)
            == Qt.CheckState.Checked
        )
        if hasattr(model, "set_checked"):
            model.set_checked(row, not checked, emit_signal=False)
        else:
            model.setData(
                model.index(row, 0),
                Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked,
                Qt.ItemDataRole.CheckStateRole,
            )

        refresh = getattr(self._window, "_refresh_update_filter_summary", None)
        if self._table is getattr(self._window, "table", None) and callable(refresh):
            refresh()
        return True


def _refresh_detail_from_selection(window, table, proxy, pane) -> None:
    if getattr(window, "_is_closing", False):
        return
    window.update_detail_pane(table, proxy, pane)


def _decouple_row_selection(window, table, proxy, pane) -> None:
    """Keep row highlighting for inspection separate from action checkboxes."""
    selection_model = table.selectionModel()
    if selection_model is not None:
        try:
            # The historical presentation connected selectionChanged to a
            # bidirectional checkbox mirror. It is the only selectionChanged
            # connection on these tables and makes ExtendedSelection erase
            # previously checked rows on an ordinary click.
            selection_model.selectionChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        selection_model.selectionChanged.connect(
            lambda _selected, _deselected: _refresh_detail_from_selection(
                window, table, proxy, pane
            )
        )

    header = table.horizontalHeader()
    header.setMinimumSectionSize(_CHECKBOX_COLUMN_WIDTH)
    table.setColumnWidth(0, _CHECKBOX_COLUMN_WIDTH)

    event_filter = _CheckboxColumnFilter(window, table, proxy)
    table.viewport().installEventFilter(event_filter)
    window._checkbox_column_filters.append(event_filter)


def set_visible_checked(window, checked: bool) -> int:
    """Set checkbox state for every currently visible Updates row."""
    proxy = window.proxy_model
    model = proxy.sourceModel()
    if model is None:
        return 0

    changed = 0
    for proxy_row in range(proxy.rowCount()):
        source_index = proxy.mapToSource(proxy.index(proxy_row, 0))
        row = source_index.row()
        if hasattr(model, "set_checked") and model.set_checked(
            row, checked, emit_signal=False
        ):
            changed += 1

    refresh = getattr(window, "_refresh_update_filter_summary", None)
    if callable(refresh):
        refresh()
    return changed


def clear_all_checked(window) -> int:
    """Clear all Updates checkboxes without disturbing row inspection selection."""
    model = window.proxy_model.sourceModel()
    if model is None:
        return 0

    changed = 0
    for row in range(len(getattr(model, "_data", []))):
        if hasattr(model, "set_checked") and model.set_checked(
            row, False, emit_signal=False
        ):
            changed += 1

    refresh = getattr(window, "_refresh_update_filter_summary", None)
    if callable(refresh):
        refresh()
    return changed


def _rewire_bulk_checkbox_controls(window) -> None:
    select_button = None
    clear_button = None
    for button in window.update_tab.findChildren(QPushButton):
        if button.text() in {"Select Visible Rows", "Select Visible", "Check Visible"}:
            select_button = button
        elif button.text() in {"Clear Selection", "Clear Selected", "Clear Checked"}:
            clear_button = button

    if select_button is not None:
        try:
            select_button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        select_button.setText("Check Visible")
        select_button.setToolTip(
            "Check every update row currently visible through the search filter"
        )
        select_button.clicked.connect(lambda: set_visible_checked(window, True))
        window.check_visible_btn = select_button

    if clear_button is not None:
        try:
            clear_button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        clear_button.setText("Clear Checked")
        clear_button.setToolTip("Clear all checked update rows")
        clear_button.clicked.connect(lambda: clear_all_checked(window))
        window.clear_checked_btn = clear_button


def apply_selection_polish(window) -> None:
    """Install reliable independent checkbox interaction after all UI layers exist."""
    if getattr(window, "_selection_polished", False):
        return
    window._selection_polished = True
    window._checkbox_column_filters = []

    _decouple_row_selection(
        window,
        window.table,
        window.proxy_model,
        window.update_details,
    )
    _decouple_row_selection(
        window,
        window.inventory_table,
        window.inventory_proxy,
        window.inventory_details,
    )
    _rewire_bulk_checkbox_controls(window)

"""Normalize table selection into one familiar Windows-style selection model.

Rows and checkboxes represent the same action set. A plain click selects one
row, Ctrl-click toggles individual rows, and Shift-click selects a contiguous
range. The first column remains a large checkbox hit target, but it follows the
same row-selection semantics as clicking anywhere else on the row.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QTimer,
    Qt,
)
from PySide6.QtWidgets import QPushButton, QTableView


_CHECKBOX_COLUMN_WIDTH = 52


class _CheckboxColumnFilter(QObject):
    """Treat the full first-column cell as a row-selection target."""

    def __init__(self, window, table, proxy):
        super().__init__(table.viewport())
        self._window = window
        self._table = table
        self._proxy = proxy
        table.destroyed.connect(self._detach_table)

    def _detach_table(self, *_args):
        self._table = None
        self._proxy = None
        self._window = None

    def _index_for_event(self, event):
        table = self._table
        if table is None:
            return None
        position = getattr(event, "position", None)
        if position is None:
            return None
        try:
            return table.indexAt(position().toPoint())
        except RuntimeError:
            self._detach_table()
            return None

    def _apply_selection(self, index, modifiers):
        table = self._table
        if table is None:
            return
        selection_model = table.selectionModel()
        model = table.model()
        if selection_model is None or model is None:
            return

        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        row_flag = QItemSelectionModel.SelectionFlag.Rows

        if shift:
            anchor = selection_model.currentIndex()
            anchor_row = anchor.row() if anchor.isValid() else index.row()
            first = min(anchor_row, index.row())
            last = max(anchor_row, index.row())
            last_column = max(0, model.columnCount() - 1)
            selection = QItemSelection(
                model.index(first, 0),
                model.index(last, last_column),
            )
            command = (
                QItemSelectionModel.SelectionFlag.Select
                if control
                else QItemSelectionModel.SelectionFlag.ClearAndSelect
            )
            selection_model.select(selection, command | row_flag)
            selection_model.setCurrentIndex(
                index,
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )
            return

        if control:
            selected = selection_model.isRowSelected(index.row(), QModelIndex())
            command = (
                QItemSelectionModel.SelectionFlag.Deselect
                if selected
                else QItemSelectionModel.SelectionFlag.Select
            )
            selection_model.select(index, command | row_flag)
            selection_model.setCurrentIndex(
                index,
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )
            return

        selection_model.select(
            index,
            QItemSelectionModel.SelectionFlag.ClearAndSelect | row_flag,
        )
        selection_model.setCurrentIndex(
            index,
            QItemSelectionModel.SelectionFlag.NoUpdate,
        )

    def eventFilter(self, watched, event):
        event_type = event.type()
        if event_type not in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        }:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        table = self._table
        if table is None:
            return False
        try:
            if watched is not table.viewport():
                return False
        except RuntimeError:
            self._detach_table()
            return False

        index = self._index_for_event(event)
        if index is None or not index.isValid() or index.column() != 0:
            return False

        # Consume release/double-click so the delegate cannot independently
        # toggle the checkbox after we have applied the row selection once.
        if event_type in {
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        }:
            return True

        self._apply_selection(index, event.modifiers())
        return True


def _refresh_detail_from_selection(window, table, proxy, pane) -> None:
    if getattr(window, "_is_closing", False):
        return
    try:
        window.update_detail_pane(table, proxy, pane)
    except RuntimeError:
        return


def _enforce_table_interaction(table) -> None:
    """Restore Windows-style multi-selection and the large checkbox target."""
    try:
        table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        header = table.horizontalHeader()
        header.setMinimumSectionSize(_CHECKBOX_COLUMN_WIDTH)
        if table.model() is not None and table.model().columnCount() > 0:
            table.setColumnWidth(0, _CHECKBOX_COLUMN_WIDTH)
    except RuntimeError:
        return


def _schedule_table_interaction(table) -> None:
    # Source-model loaders resize the checkbox column after sourceModelChanged.
    # Re-apply on the next event-loop turn so the final geometry is ours.
    QTimer.singleShot(0, lambda: _enforce_table_interaction(table))


def _selection_key(window, model, item):
    helper = getattr(window, "_selection_key", None)
    if callable(helper):
        return helper(model, item)
    return item.get("Id") or item.get("Name")


def _checked_source_items(window, proxy) -> list[dict]:
    model = proxy.sourceModel() if proxy is not None else None
    if model is None:
        return []
    selected = getattr(model, "_selected", {})
    return [
        item
        for item in getattr(model, "_data", [])
        if bool(selected.get(_selection_key(window, model, item), False))
    ]


def _checked_count_for_current_page(window) -> int:
    proxy = window.inventory_proxy if window.sidebar.currentRow() == 1 else window.proxy_model
    return len(_checked_source_items(window, proxy))


def _refresh_selected_action_state(window) -> None:
    button = getattr(window, "update_selected_btn", None)
    if button is None:
        return
    count = _checked_count_for_current_page(window)
    button.setText("Update Selected" if count == 0 else f"Update Selected ({count})")


def _sync_selection_to_checkboxes(window, table, proxy, pane) -> None:
    """Mirror the table's selected rows into checkbox state exactly."""
    model = proxy.sourceModel() if proxy is not None else None
    selection_model = table.selectionModel()
    if model is None or selection_model is None or getattr(model, "_syncing", False):
        return

    selected_rows = {
        proxy.mapToSource(index).row()
        for index in selection_model.selectedRows()
        if index.isValid()
    }
    try:
        model._syncing = True
        for row in range(len(getattr(model, "_data", []))):
            model.set_checked(row, row in selected_rows, emit_signal=False)
    finally:
        model._syncing = False

    _refresh_detail_from_selection(window, table, proxy, pane)
    refresh = getattr(window, "_refresh_update_filter_summary", None)
    if table is getattr(window, "table", None) and callable(refresh):
        refresh()
    _refresh_selected_action_state(window)


def _wire_table_selection(window, table, proxy, pane) -> None:
    _enforce_table_interaction(table)
    selection_model = table.selectionModel()
    if selection_model is not None:
        try:
            selection_model.selectionChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        selection_model.selectionChanged.connect(
            lambda _selected, _deselected: _sync_selection_to_checkboxes(
                window, table, proxy, pane
            )
        )

    proxy.sourceModelChanged.connect(lambda: _schedule_table_interaction(table))
    proxy.sourceModelChanged.connect(
        lambda: QTimer.singleShot(0, lambda: _refresh_selected_action_state(window))
    )

    event_filter = _CheckboxColumnFilter(window, table, proxy)
    table.viewport().installEventFilter(event_filter)
    window._checkbox_column_filters.append(event_filter)


def _native_checkbox_to_selection(window, table, proxy, source_row, checked) -> None:
    """Make keyboard/native checkbox toggles update the same row selection."""
    model = proxy.sourceModel()
    selection_model = table.selectionModel()
    if model is None or selection_model is None or getattr(model, "_syncing", False):
        return
    proxy_index = proxy.mapFromSource(model.index(source_row, 0))
    if not proxy_index.isValid():
        return
    command = (
        QItemSelectionModel.SelectionFlag.Select
        if checked
        else QItemSelectionModel.SelectionFlag.Deselect
    )
    selection_model.select(
        proxy_index,
        command | QItemSelectionModel.SelectionFlag.Rows,
    )
    selection_model.setCurrentIndex(
        proxy_index,
        QItemSelectionModel.SelectionFlag.NoUpdate,
    )


def update_selected(window) -> None:
    """Update exactly the rows represented by the synchronized selection/checks."""
    on_updates = window.sidebar.currentRow() == 0
    proxy = window.proxy_model if on_updates else window.inventory_proxy
    selected_items = _checked_source_items(window, proxy)
    if not selected_items:
        window.status_label.setText("Select one or more packages to update")
        window.logger.info("Update Selected clicked with no selected packages.")
        return

    if on_updates:
        refs = []
        seen = set()
        for item in selected_items:
            if not window._is_winget_update_item(item):
                continue
            ref = window._package_ref_for_winget_item(item)
            if ref is None:
                continue
            key = window._package_ref_key(ref)
            if key not in seen:
                refs.append(ref)
                seen.add(key)
    else:
        refs = window._winget_refs_for_inventory_items(selected_items)

    if refs:
        window.logger.info(
            "User requested update for %d selected Winget-proven app(s).",
            len(refs),
        )
        window.batch_update(refs)
        return

    message = (
        "Selected app(s) are not present in the current authoritative Winget "
        "upgrade scan; no update command was run."
    )
    window.status_label.setText(message)
    window.logger.warning(message)
    window.append_log(f"\n[!] {message}")


def select_visible(window) -> int:
    """Select every currently visible Updates row and mirror the checkboxes."""
    proxy = window.proxy_model
    selection_model = window.table.selectionModel()
    if selection_model is None or proxy.rowCount() == 0:
        return 0
    last_column = max(0, proxy.columnCount() - 1)
    selection = QItemSelection(
        proxy.index(0, 0),
        proxy.index(proxy.rowCount() - 1, last_column),
    )
    selection_model.select(
        selection,
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    return proxy.rowCount()


def clear_selection(window) -> int:
    """Clear the Updates row selection and therefore all mirrored checks."""
    model = window.proxy_model.sourceModel()
    before = len(_checked_source_items(window, window.proxy_model))
    selection_model = window.table.selectionModel()
    if selection_model is not None:
        selection_model.clearSelection()
    elif model is not None:
        for row in range(len(getattr(model, "_data", []))):
            model.set_checked(row, False, emit_signal=False)
    _refresh_selected_action_state(window)
    return before


def _rewire_bulk_controls(window) -> None:
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
        select_button.setText("Select Visible")
        select_button.setToolTip("Select every update row currently visible through the filter")
        select_button.clicked.connect(lambda: select_visible(window))
        window.check_visible_btn = select_button

    if clear_button is not None:
        try:
            clear_button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        clear_button.setText("Clear Selection")
        clear_button.setToolTip("Clear all selected update rows")
        clear_button.clicked.connect(lambda: clear_selection(window))
        window.clear_checked_btn = clear_button

    try:
        window.update_selected_btn.clicked.disconnect()
    except (RuntimeError, TypeError):
        pass
    window.update_selected_btn.setText("Update Selected")
    window.update_selected_btn.setToolTip("Update the selected/checked package rows")
    window.update_selected_btn.clicked.connect(window.update_selected)


def apply_selection_polish(window) -> None:
    """Install unified row/checkbox selection after all UI layers exist."""
    if getattr(window, "_selection_polished", False):
        return
    window._selection_polished = True
    window._checkbox_column_filters = []

    window.handle_native_checkbox = lambda table, proxy, row, checked: (
        _native_checkbox_to_selection(window, table, proxy, row, checked)
    )
    window.update_selected = lambda: update_selected(window)

    _wire_table_selection(
        window,
        window.table,
        window.proxy_model,
        window.update_details,
    )
    _wire_table_selection(
        window,
        window.inventory_table,
        window.inventory_proxy,
        window.inventory_details,
    )
    _rewire_bulk_controls(window)
    window.sidebar.currentRowChanged.connect(
        lambda _index: _refresh_selected_action_state(window)
    )
    _refresh_selected_action_state(window)

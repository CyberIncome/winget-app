"""Final checkbox/row-selection interaction normalization for the product UI.

Rows are for inspection; checkboxes are the explicit package-action selection.
The two states intentionally do not mirror each other.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QItemSelectionModel, QObject, QTimer, Qt
from PySide6.QtWidgets import QPushButton, QTableView


_CHECKBOX_COLUMN_WIDTH = 52


class _CheckboxColumnFilter(QObject):
    """Make the full first-column cell a reliable checkbox hit target."""

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
        proxy = self._proxy
        window = self._window
        if table is None or proxy is None:
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

        # A native double-click sequence should still represent one checkbox
        # action, not toggle-on/toggle-off in rapid succession.
        if event_type in {
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        }:
            return True

        try:
            model = proxy.sourceModel()
        except RuntimeError:
            self._detach_table()
            return False
        if model is None:
            return True
        source_index = proxy.mapToSource(index)
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

        # Checkbox action changes the action set, but also moves the single
        # inspection highlight/details to the row the user just interacted with.
        # It never changes any other row's checkbox state.
        selection_model = table.selectionModel()
        if selection_model is not None:
            selection_model.setCurrentIndex(
                index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )

        if window is not None:
            pane = (
                getattr(window, "update_details", None)
                if table is getattr(window, "table", None)
                else getattr(window, "inventory_details", None)
            )
            if pane is not None:
                _refresh_detail_from_selection(window, table, proxy, pane)
            refresh = getattr(window, "_refresh_update_filter_summary", None)
            if table is getattr(window, "table", None) and callable(refresh):
                refresh()
            _refresh_checked_action_state(window)
        return True


def _refresh_detail_from_selection(window, table, proxy, pane) -> None:
    if getattr(window, "_is_closing", False):
        return
    try:
        window.update_detail_pane(table, proxy, pane)
    except RuntimeError:
        return


def _enforce_checkbox_column_width(table) -> None:
    """Restore the full-cell checkbox hit target after model replacement."""
    try:
        header = table.horizontalHeader()
        header.setMinimumSectionSize(_CHECKBOX_COLUMN_WIDTH)
        if table.model() is not None and table.model().columnCount() > 0:
            table.setColumnWidth(0, _CHECKBOX_COLUMN_WIDTH)
    except RuntimeError:
        return


def _schedule_checkbox_column_width(table) -> None:
    QTimer.singleShot(0, lambda: _enforce_checkbox_column_width(table))


def _decouple_row_selection(window, table, proxy, pane) -> None:
    """Make row highlighting a single inspection cursor, not an action set."""
    table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
    table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)

    selection_model = table.selectionModel()
    if selection_model is not None:
        try:
            # Remove the historical bidirectional checkbox mirror.
            selection_model.selectionChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        selection_model.selectionChanged.connect(
            lambda _selected, _deselected: _refresh_detail_from_selection(
                window, table, proxy, pane
            )
        )

    _enforce_checkbox_column_width(table)
    proxy.sourceModelChanged.connect(lambda: _schedule_checkbox_column_width(table))
    proxy.sourceModelChanged.connect(
        lambda: QTimer.singleShot(0, lambda: _refresh_checked_action_state(window))
    )

    event_filter = _CheckboxColumnFilter(window, table, proxy)
    table.viewport().installEventFilter(event_filter)
    window._checkbox_column_filters.append(event_filter)


def _independent_native_checkbox(window, table, proxy, source_row, checked) -> None:
    """Handle keyboard/native checkbox toggles without touching row selection."""
    if table is getattr(window, "table", None):
        refresh = getattr(window, "_refresh_update_filter_summary", None)
        if callable(refresh):
            refresh()
    _refresh_checked_action_state(window)


def _checked_source_items(window, table, proxy) -> list[dict]:
    model = proxy.sourceModel() if proxy is not None else None
    if model is None:
        return []
    return [
        item
        for item in getattr(model, "_data", [])
        if bool(
            getattr(model, "_selected", {}).get(
                window._selection_key(model, item),
                False,
            )
        )
    ]


def _checked_count_for_current_page(window) -> int:
    if window.sidebar.currentRow() == 1:
        return len(
            _checked_source_items(
                window,
                window.inventory_table,
                window.inventory_proxy,
            )
        )
    return len(
        _checked_source_items(
            window,
            window.table,
            window.proxy_model,
        )
    )


def _refresh_checked_action_state(window) -> None:
    button = getattr(window, "update_selected_btn", None)
    if button is None:
        return
    count = _checked_count_for_current_page(window)
    button.setText("Update Checked" if count == 0 else f"Update Checked ({count})")


def update_checked(window) -> None:
    """Update only explicit checkbox selections; highlights are inspection-only."""
    on_updates = window.sidebar.currentRow() == 0
    proxy = window.proxy_model if on_updates else window.inventory_proxy
    table = window.table if on_updates else window.inventory_table
    selected_items = _checked_source_items(window, table, proxy)
    if not selected_items:
        window.status_label.setText("Check one or more packages to update")
        window.logger.info("Update Checked clicked with no checked packages.")
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
            "User requested update for %d explicitly checked Winget-proven app(s).",
            len(refs),
        )
        window.batch_update(refs)
        return

    message = (
        "Checked app(s) are not present in the current authoritative Winget "
        "upgrade scan; no update command was run."
    )
    window.status_label.setText(message)
    window.logger.warning(message)
    window.append_log(f"\n[!] {message}")


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
    _refresh_checked_action_state(window)
    return changed


def clear_all_checked(window) -> int:
    """Clear all Updates checkboxes without disturbing inspection highlight."""
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
    _refresh_checked_action_state(window)
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

    try:
        window.update_selected_btn.clicked.disconnect()
    except (RuntimeError, TypeError):
        pass
    window.update_selected_btn.setToolTip(
        "Update only explicitly checked packages; row highlight is inspection-only"
    )
    window.update_selected_btn.clicked.connect(window.update_selected)


def apply_selection_polish(window) -> None:
    """Install independent checklist + single-row inspection behavior."""
    if getattr(window, "_selection_polished", False):
        return
    window._selection_polished = True
    window._checkbox_column_filters = []

    # Existing model signals call self.handle_native_checkbox dynamically. Point
    # that callback at the independent policy so keyboard toggles cannot revive
    # the legacy checkbox<->row-selection mirroring behavior.
    window.handle_native_checkbox = lambda table, proxy, row, checked: (
        _independent_native_checkbox(window, table, proxy, row, checked)
    )
    # Preserve the historical public method name for callers/shortcuts, but make
    # its canonical instance behavior checklist-only as well.
    window.update_selected = lambda: update_checked(window)

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
    window.sidebar.currentRowChanged.connect(
        lambda _index: _refresh_checked_action_state(window)
    )
    _refresh_checked_action_state(window)

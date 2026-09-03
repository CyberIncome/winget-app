"""Normalize table selection into one familiar Windows-style selection model.

Rows and checkboxes represent the same action set. Qt's native ExtendedSelection
engine owns every mouse click, including clicks over the checkbox column. The
checkboxes are display-only mirrors of selected rows; they do not implement a
second mouse-selection path.
"""

from __future__ import annotations

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QTimer, Qt
from PySide6.QtWidgets import QPushButton, QStyledItemDelegate, QTableView


_CHECKBOX_COLUMN_WIDTH = 52


class _SelectionMirrorDelegate(QStyledItemDelegate):
    """Render checkbox state without letting the delegate toggle it directly.

    QTableView must receive the complete mouse press/release sequence so its
    native ExtendedSelection implementation can apply plain, Ctrl, and Shift
    semantics correctly. Returning ``False`` for editor events in column zero
    keeps the check indicator visible while making it non-interactive; the
    selectionChanged signal is the sole writer of checkbox state.
    """

    def editorEvent(self, event, model, option, index):
        if index.isValid() and index.column() == 0:
            return False
        return super().editorEvent(event, model, option, index)


def _refresh_detail_from_selection(window, table, proxy, pane) -> None:
    if getattr(window, "_is_closing", False):
        return
    try:
        window.update_detail_pane(table, proxy, pane)
    except RuntimeError:
        return


def _repaint_table_viewport(table) -> None:
    """Repaint the whole visible table after selection/check mirroring settles."""
    try:
        table.viewport().update()
    except RuntimeError:
        return


def _queue_full_selection_repaint(table) -> None:
    """Repaint after the current selection signal finishes dispatching.

    Mirroring row selection into CheckStateRole emits per-checkbox dataChanged
    signals synchronously. On Windows/Qt those cell repaints can race the view's
    deferred full-row selection repaint, leaving only part of a selected row in
    its final visual state until mouse hover triggers another paint. Queue one
    viewport-wide update for the next event-loop turn so every visible cell is
    painted from the settled selection model immediately.
    """
    QTimer.singleShot(0, lambda: _repaint_table_viewport(table))


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
    proxy = (
        window.inventory_proxy
        if window.sidebar.currentRow() == 1
        else window.proxy_model
    )
    return len(_checked_source_items(window, proxy))


def _refresh_selected_action_state(window) -> None:
    button = getattr(window, "update_selected_btn", None)
    if button is None:
        return
    count = _checked_count_for_current_page(window)
    button.setText(
        "Update Selected" if count == 0 else f"Update Selected ({count})"
    )


def _sync_selection_to_checkboxes(window, table, proxy, pane) -> None:
    """Mirror the table's selected rows into checkbox state exactly."""
    model = proxy.sourceModel() if proxy is not None else None
    selection_model = table.selectionModel()
    if (
        model is None
        or selection_model is None
        or getattr(model, "_syncing", False)
    ):
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
    _queue_full_selection_repaint(table)


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
        lambda: QTimer.singleShot(
            0, lambda: _refresh_selected_action_state(window)
        )
    )

    # Do not intercept viewport mouse events. Qt needs both press and release to
    # collapse an existing range on a subsequent plain click. A display-only
    # delegate prevents the checkbox itself from becoming a competing input.
    delegate = _SelectionMirrorDelegate(table)
    table.setItemDelegateForColumn(0, delegate)
    window._selection_mirror_delegates.append(delegate)


def _native_checkbox_to_selection(
    window, table, proxy, source_row, checked
) -> None:
    """Keep any programmatic checkbox changes aligned with row selection."""
    model = proxy.sourceModel()
    selection_model = table.selectionModel()
    if (
        model is None
        or selection_model is None
        or getattr(model, "_syncing", False)
    ):
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
    """Update exactly the rows represented by synchronized selection/checks."""
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
    """Select every currently visible Updates row and mirror checkboxes."""
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
    """Clear Updates row selection and therefore all mirrored checks."""
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
        if button.text() in {
            "Select Visible Rows",
            "Select Visible",
            "Check Visible",
        }:
            select_button = button
        elif button.text() in {
            "Clear Selection",
            "Clear Selected",
            "Clear Checked",
        }:
            clear_button = button

    if select_button is not None:
        try:
            select_button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        select_button.setText("Select Visible")
        select_button.setToolTip(
            "Select every update row currently visible through the filter"
        )
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
    window.update_selected_btn.setToolTip(
        "Update the selected/checked package rows"
    )
    window.update_selected_btn.clicked.connect(window.update_selected)


def apply_selection_polish(window) -> None:
    """Install unified native row/checkbox selection after all UI layers exist."""
    if getattr(window, "_selection_polished", False):
        return
    window._selection_polished = True
    window._selection_mirror_delegates = []
    # Retained as an empty compatibility attribute for older diagnostics/tests;
    # no viewport mouse filter participates in selection anymore.
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

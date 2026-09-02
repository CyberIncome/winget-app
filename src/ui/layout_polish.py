"""Post-construction layout normalization for the canonical product window.

The application intentionally builds its feature set in additive subclasses.
This module runs once after construction so those independently useful layers
share one coherent geometry instead of competing for vertical/horizontal space.
No package-management behavior lives here.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
)


def _repolish(widget) -> None:
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def _mark_compact(button: QPushButton) -> None:
    button.setProperty("compact", True)
    button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    _repolish(button)


def _find_layout_with_widget(layout, target):
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is target:
            return layout
        nested = item.layout()
        if nested is not None:
            found = _find_layout_with_widget(nested, target)
            if found is not None:
                return found
    return None


def _polish_header(window) -> None:
    window.setMinimumSize(960, 680)

    warning = getattr(window, "admin_warning", None)
    if warning is not None:
        warning.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        warning.setMaximumWidth(max(130, warning.sizeHint().width() + 20))
        warning.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    search = window.search_bar
    # Undo the historical fixed 360 px width so the header can compress.
    search.setMinimumWidth(200)
    search.setMaximumWidth(360)
    search.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    for card in (
        window.stat_installed,
        window.stat_updates,
        window.stat_unknown,
        window.stat_scan,
    ):
        card.setMinimumHeight(70)
        card.setMaximumHeight(88)


def _polish_navigation(window) -> None:
    window.sidebar.setMinimumWidth(170)
    window.sidebar.setMaximumWidth(220)
    splitter = window.sidebar.parentWidget()
    if isinstance(splitter, QSplitter):
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(3)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([190, 1210])


def _polish_content_splitter(splitter, table, details) -> None:
    splitter.setChildrenCollapsible(False)
    splitter.setHandleWidth(4)
    splitter.setStretchFactor(0, 4)
    splitter.setStretchFactor(1, 1)
    table.setMinimumWidth(520)
    details.setMinimumWidth(250)
    details.setMaximumWidth(440)
    details.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    splitter.setSizes([1000, 340])


def _polish_updates_toolbar(window) -> None:
    update_layout = window.update_tab.layout()
    if update_layout is None or update_layout.count() < 2:
        return

    toolbar = update_layout.itemAt(0).widget()
    if toolbar is None:
        return
    window.updates_toolbar = toolbar
    toolbar.setObjectName("updatesToolbar")
    toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    toolbar.setMinimumHeight(38)
    toolbar.setMaximumHeight(52)
    toolbar.setToolTip(
        "Double-click = read-only details. Package installation starts only from "
        "the explicit Update controls."
    )

    # The long inline hint was useful while developing the new interaction
    # model, but it competes with actual controls at normal window widths.
    for label in toolbar.findChildren(type(window.update_filter_summary)):
        if label is window.update_filter_summary:
            continue
        if "Double-click" in label.text():
            label.hide()

    replacements = {
        "Select Visible Rows": "Select Visible",
        "Clear Selection": "Clear Selected",
        "Clear Search": "Clear Search",
    }
    for button in toolbar.findChildren(QPushButton):
        if button.text() in replacements:
            button.setText(replacements[button.text()])
            _mark_compact(button)

    window.update_filter_summary.setMinimumWidth(0)
    window.update_filter_summary.setSizePolicy(
        QSizePolicy.Expanding, QSizePolicy.Preferred
    )

    update_layout.setContentsMargins(10, 6, 10, 8)
    update_layout.setSpacing(8)
    update_layout.setStretch(0, 0)
    update_layout.setStretch(1, 1)


def _wrap_settings_page(window) -> None:
    if hasattr(window, "settings_scroll"):
        return
    index = window.stack.indexOf(window.settings_tab)
    if index < 0:
        return

    was_current = window.stack.currentIndex() == index
    window.stack.removeWidget(window.settings_tab)

    scroll = QScrollArea()
    scroll.setObjectName("settingsScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(window.settings_tab)
    window.stack.insertWidget(index, scroll)
    window.settings_scroll = scroll

    settings_layout = window.settings_tab.layout()
    if settings_layout is not None:
        settings_layout.setContentsMargins(20, 18, 20, 18)
        settings_layout.setSpacing(12)

    if was_current:
        window.stack.setCurrentIndex(index)


def _polish_footer(window) -> None:
    panel = window.console.parentWidget()
    if panel is None:
        return
    root_layout = panel.layout()
    if not isinstance(root_layout, QBoxLayout):
        return

    window.bottom_action_panel = panel
    panel.setObjectName("actionBar")
    panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

    # The historical footer was a horizontal console plus a *vertical* stack
    # of five buttons. That consumed ~200 px even with the console hidden.
    # Make the footer console-over-actions and keep the action strip one row.
    root_layout.setDirection(QBoxLayout.TopToBottom)
    root_layout.setContentsMargins(16, 6, 16, 8)
    root_layout.setSpacing(7)

    actions = _find_layout_with_widget(root_layout, window.refresh_btn)
    if isinstance(actions, QBoxLayout):
        actions.setDirection(QBoxLayout.LeftToRight)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(7)

        # Remove the old widget ordering but leave the widgets alive/reparented.
        while actions.count():
            actions.takeAt(0)

        ordered = (
            window.refresh_btn,
            window.scan_inventory_btn,
            window.toggle_console_btn,
            window.update_selected_btn,
            window.update_all_btn,
        )
        for button in ordered:
            _mark_compact(button)

        actions.addWidget(window.refresh_btn)
        actions.addWidget(window.scan_inventory_btn)
        actions.addStretch(1)
        actions.addWidget(window.toggle_console_btn)
        actions.addWidget(window.update_selected_btn)
        actions.addWidget(window.update_all_btn)
        actions.setAlignment(Qt.AlignVCenter)

    window.console.setMinimumHeight(130)
    window.console.setMaximumHeight(210)
    window.console.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    sync_console_panel(window)

    # toggle_console() runs first (it was connected by the legacy UI), then
    # this callback recomputes the panel constraint from the new visibility.
    window.toggle_console_btn.clicked.connect(
        lambda: QTimer.singleShot(0, lambda: sync_console_panel(window))
    )


def sync_console_panel(window) -> None:
    panel = getattr(window, "bottom_action_panel", None)
    if panel is None:
        return
    if window.console.isVisible():
        panel.setMinimumHeight(165)
        panel.setMaximumHeight(260)
    else:
        panel.setMinimumHeight(0)
        panel.setMaximumHeight(58)
    panel.updateGeometry()


def apply_layout_polish(window) -> None:
    """Normalize the fully constructed product UI into one responsive layout."""
    if getattr(window, "_final_layout_polished", False):
        return
    window._final_layout_polished = True

    _polish_header(window)
    _polish_navigation(window)
    _polish_updates_toolbar(window)
    _polish_content_splitter(
        window.update_splitter,
        window.table,
        window.update_details,
    )
    _polish_content_splitter(
        window.inventory_splitter,
        window.inventory_table,
        window.inventory_details,
    )

    update_layout = window.update_tab.layout()
    if update_layout is not None:
        update_layout.setStretch(update_layout.indexOf(window.update_splitter), 1)
    inventory_layout = window.inventory_tab.layout()
    if inventory_layout is not None:
        inventory_layout.setContentsMargins(10, 6, 10, 8)
        inventory_layout.setSpacing(8)
        inventory_layout.setStretch(
            inventory_layout.indexOf(window.inventory_splitter), 1
        )

    _wrap_settings_page(window)
    _polish_footer(window)

    # Re-apply splitter ratios after the first real layout pass; doing this at
    # construction time alone can be ignored while the window is still 0 px.
    QTimer.singleShot(
        0,
        lambda: (
            window.update_splitter.setSizes([1000, 340]),
            window.inventory_splitter.setSizes([1000, 340]),
        ),
    )

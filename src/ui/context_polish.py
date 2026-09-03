"""Context-aware GUI polish layered after final geometry normalization.

This module intentionally owns presentation only: page-specific action visibility,
search affordances, and a structured version-mapping review dialog. It must not
contain package execution or parser logic.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


def _apply_page_context(window, index: int) -> None:
    """Show controls only on pages where their meaning is unambiguous."""
    table_page = index in (0, 1)
    window.search_bar.setVisible(table_page)
    window.update_selected_btn.setVisible(table_page)
    # Update All always acts on the authoritative Updates table, so showing it
    # while Inventory is active is misleading even though the command is safe.
    window.update_all_btn.setVisible(index == 0)

    if index == 0:
        window.search_bar.setPlaceholderText("Search updates (Ctrl+F)...")
        window.update_selected_btn.setToolTip(
            "Update the selected rows; checkboxes mirror the same selection"
        )
        window.update_all_btn.setToolTip(
            "Update every package proven upgradeable by the current Winget scan"
        )
    elif index == 1:
        window.search_bar.setPlaceholderText("Search inventory (Ctrl+F)...")
        window.update_selected_btn.setToolTip(
            "Update selected inventory apps that map unambiguously to current "
            "Winget upgrade rows"
        )


def _review_details(item: dict) -> str:
    lines = [
        str(item.get("Name") or item.get("Id") or "Package"),
        f"Package ID: {item.get('Id') or 'unavailable'}",
        f"Source: {item.get('Source') or 'unavailable'}",
        "",
        f"Installed (Windows): {item.get('Version') or 'unknown'}",
        f"Installed (WinGet source mapping): {item.get('SourceInstalledVersion') or 'unknown'}",
        f"Target (WinGet package): {item.get('Available') or 'unknown'}",
        f"Assessment: {item.get('VersionStatus') or 'review'}",
        "",
        str(item.get("VersionExplanation") or "Version schemes do not compare cleanly."),
        "",
        "WinGet still reports this package as upgradeable. The dashboard will only "
        "target the exact package/source/version shown by the current scan.",
    ]
    return "\n".join(lines)


def build_version_review_dialog(window) -> QDialog:
    """Build a bounded, inspectable review dialog for suspicious version mappings."""
    rows = list(window._version_review_rows())

    dialog = QDialog(window)
    dialog.setObjectName("versionReviewDialog")
    dialog.setWindowTitle("Version Mapping Review")
    dialog.resize(920, 600)
    dialog.setMinimumSize(720, 460)
    dialog.setStyleSheet(
        "QDialog#versionReviewDialog { background-color: #11131c; }"
        "QPlainTextEdit#versionReviewDetails {"
        " background-color: rgba(13, 15, 24, 0.94);"
        " border: 1px solid #414868; border-radius: 8px; padding: 10px;"
        " font-family: 'Cascadia Code', 'Consolas', monospace; color: #cdd6f4;"
        "}"
    )

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)

    intro = QLabel(
        "WinGet still reports these packages as upgradeable, but Windows and "
        "WinGet version strings do not safely compare as one numbering scheme. "
        "Select a row to inspect the mapping before updating."
    )
    intro.setObjectName("apiStatusHint")
    intro.setWordWrap(True)
    layout.addWidget(intro)

    table = QTableWidget(len(rows), 5, dialog)
    table.setObjectName("versionReviewTable")
    table.setHorizontalHeaderLabels(
        ["Package", "Windows", "WinGet Installed", "Target", "Assessment"]
    )
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)

    for row_index, item in enumerate(rows):
        values = (
            item.get("Name") or item.get("Id") or "Package",
            item.get("Version") or "unknown",
            item.get("SourceInstalledVersion") or "unknown",
            item.get("Available") or "unknown",
            item.get("VersionStatus") or "review",
        )
        for column, value in enumerate(values):
            cell = QTableWidgetItem(str(value))
            if column > 0:
                cell.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
            table.setItem(row_index, column, cell)

    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for column in range(1, 5):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    layout.addWidget(table, 1)

    details = QPlainTextEdit(dialog)
    details.setObjectName("versionReviewDetails")
    details.setReadOnly(True)
    details.setMinimumHeight(130)
    details.setMaximumHeight(190)
    layout.addWidget(details)

    def show_row(row: int, _column: int = 0, *_args) -> None:
        if 0 <= row < len(rows):
            details.setPlainText(_review_details(rows[row]))
        else:
            details.setPlainText("No version-mapping row selected.")

    table.currentCellChanged.connect(show_row)
    if rows:
        table.selectRow(0)
        show_row(0)
    else:
        details.setPlainText("No current WinGet rows require version-mapping review.")

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return dialog


def show_version_review_dialog(window) -> None:
    dialog = build_version_review_dialog(window)
    dialog.exec()


def apply_context_polish(window) -> None:
    """Install final page-context behavior once after layout construction."""
    if getattr(window, "_context_polished", False):
        return
    window._context_polished = True

    window.sidebar.currentRowChanged.connect(
        lambda index: _apply_page_context(window, index)
    )
    _apply_page_context(window, window.sidebar.currentRow())

    review_button = getattr(window, "version_review_btn", None)
    if review_button is not None:
        try:
            review_button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        review_button.clicked.connect(lambda: show_version_review_dialog(window))

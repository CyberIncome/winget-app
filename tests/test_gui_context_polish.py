from PySide6.QtWidgets import QPlainTextEdit, QTableWidget

from src.ui.context_polish import (
    apply_context_polish,
    build_version_review_dialog,
)
from src.ui.layout_polish import apply_layout_polish
from src.ui.selection_polish import apply_selection_polish
from src.ui.version_integrity_window import VersionIntegrityMainWindow


def _window(qtbot):
    window = VersionIntegrityMainWindow()
    qtbot.addWidget(window)
    apply_layout_polish(window)
    apply_context_polish(window)
    apply_selection_polish(window)
    return window


def test_table_actions_and_search_hide_on_settings_and_history(qtbot):
    window = _window(qtbot)

    window.sidebar.setCurrentRow(2)
    assert window.search_bar.isHidden()
    assert window.update_selected_btn.isHidden()
    assert window.update_all_btn.isHidden()

    window.sidebar.setCurrentRow(3)
    assert window.search_bar.isHidden()
    assert window.update_selected_btn.isHidden()
    assert window.update_all_btn.isHidden()


def test_updates_and_inventory_expose_only_actions_that_match_page_context(qtbot):
    window = _window(qtbot)

    window.sidebar.setCurrentRow(0)
    assert not window.search_bar.isHidden()
    assert not window.update_selected_btn.isHidden()
    assert not window.update_all_btn.isHidden()
    assert window.update_selected_btn.text() == "Update Selected"
    assert window.search_bar.placeholderText() == "Search updates (Ctrl+F)..."
    assert "checkboxes mirror" in window.update_selected_btn.toolTip()

    window.sidebar.setCurrentRow(1)
    assert not window.search_bar.isHidden()
    assert not window.update_selected_btn.isHidden()
    assert window.update_all_btn.isHidden()
    assert window.update_selected_btn.text() == "Update Selected"
    assert window.search_bar.placeholderText() == "Search inventory (Ctrl+F)..."
    assert "selected inventory apps" in window.update_selected_btn.toolTip()


def test_version_review_dialog_is_structured_and_bounded(qtbot):
    window = _window(qtbot)
    window.apply_winget_results(
        [
            {
                "Name": "Battle.net",
                "Id": "Blizzard.BattleNet",
                "Version": "2.52.10.17731",
                "Available": "1.19.3.3219",
                "Source": "winget",
            }
        ]
    )

    dialog = build_version_review_dialog(window)
    qtbot.addWidget(dialog)
    table = dialog.findChild(QTableWidget, "versionReviewTable")
    details = dialog.findChild(QPlainTextEdit, "versionReviewDetails")

    assert table is not None
    assert details is not None
    assert table.rowCount() == 1
    assert table.columnCount() == 5
    assert table.horizontalHeaderItem(0).text() == "Package"
    assert table.horizontalHeaderItem(3).text() == "Target"
    assert table.item(0, 0).text() == "Battle.net"
    assert "Battle.net" in details.toPlainText()
    assert "Target (WinGet package): 1.19.3.3219" in details.toPlainText()
    assert dialog.minimumWidth() <= 720
    assert dialog.minimumHeight() <= 460


def test_context_polish_is_idempotent(qtbot):
    window = _window(qtbot)
    apply_context_polish(window)
    assert window._context_polished is True

from PySide6.QtWidgets import QApplication, QBoxLayout, QScrollArea

from src.ui.layout_polish import apply_layout_polish, sync_console_panel
from src.ui.version_integrity_window import VersionIntegrityMainWindow


def _polished_window(qtbot):
    window = VersionIntegrityMainWindow()
    qtbot.addWidget(window)
    apply_layout_polish(window)
    return window


def test_updates_toolbar_is_compact_and_main_splitter_keeps_space(qtbot):
    window = _polished_window(qtbot)

    assert window.updates_toolbar.maximumHeight() <= 52
    assert window.updates_toolbar.minimumHeight() <= 40
    layout = window.update_tab.layout()
    assert layout.stretch(0) == 0
    assert layout.stretch(layout.indexOf(window.update_splitter)) == 1
    assert window.update_details.minimumWidth() >= 240
    assert window.update_details.maximumWidth() <= 450
    assert window.table.minimumWidth() >= 500
    assert window.update_splitter.childrenCollapsible() is False


def test_normal_desktop_geometry_cannot_recreate_giant_dead_space(qtbot):
    window = _polished_window(qtbot)
    window.resize(1400, 900)
    window.show()
    QApplication.processEvents()

    page_height = window.update_tab.height()
    assert page_height > 300
    assert window.updates_toolbar.height() <= 52
    assert window.update_splitter.height() >= int(page_height * 0.78)
    assert window.bottom_action_panel.height() <= 60


def test_footer_is_one_action_row_when_console_hidden(qtbot):
    window = _polished_window(qtbot)

    panel = window.bottom_action_panel
    root_layout = panel.layout()
    assert isinstance(root_layout, QBoxLayout)
    assert root_layout.direction() == QBoxLayout.TopToBottom
    assert window.console.isHidden()
    assert panel.maximumHeight() <= 60

    action_layout = None
    for index in range(root_layout.count()):
        nested = root_layout.itemAt(index).layout()
        if nested is not None:
            action_layout = nested
            break
    assert isinstance(action_layout, QBoxLayout)
    assert action_layout.direction() == QBoxLayout.LeftToRight
    assert [
        window.refresh_btn.isHidden(),
        window.scan_inventory_btn.isHidden(),
        window.toggle_console_btn.isHidden(),
        window.update_selected_btn.isHidden(),
        window.update_all_btn.isHidden(),
    ] == [False, False, False, False, False]


def test_console_expands_footer_only_while_visible(qtbot):
    window = _polished_window(qtbot)
    panel = window.bottom_action_panel

    window.console.show()
    sync_console_panel(window)
    assert panel.minimumHeight() >= 160
    assert panel.maximumHeight() <= 260

    window.console.hide()
    sync_console_panel(window)
    assert panel.minimumHeight() == 0
    assert panel.maximumHeight() <= 60


def test_settings_page_is_scrollable_after_feature_layers_expand_it(qtbot):
    window = _polished_window(qtbot)

    assert isinstance(window.settings_scroll, QScrollArea)
    assert window.settings_scroll.widget() is window.settings_tab
    assert window.stack.widget(2) is window.settings_scroll
    assert window.settings_scroll.widgetResizable() is True


def test_sidebar_navigation_indices_survive_settings_wrapper(qtbot):
    window = _polished_window(qtbot)

    window.sidebar.setCurrentRow(2)
    assert window.stack.currentWidget() is window.settings_scroll

    window.sidebar.setCurrentRow(3)
    assert window.stack.currentWidget() is window.history_view.parentWidget()

    window.sidebar.setCurrentRow(0)
    assert window.stack.currentWidget() is window.update_tab


def test_header_and_navigation_no_longer_force_excess_width(qtbot):
    window = _polished_window(qtbot)

    assert window.minimumWidth() <= 960
    assert window.search_bar.minimumWidth() <= 200
    assert window.search_bar.maximumWidth() <= 360
    assert window.sidebar.minimumWidth() <= 170
    assert window.sidebar.maximumWidth() <= 220
    if hasattr(window, "admin_warning"):
        assert window.admin_warning.maximumWidth() < 250


def test_layout_polish_is_idempotent(qtbot):
    window = _polished_window(qtbot)
    panel = window.bottom_action_panel
    settings_scroll = window.settings_scroll

    apply_layout_polish(window)

    assert window.bottom_action_panel is panel
    assert window.settings_scroll is settings_scroll
    assert window.stack.widget(2) is settings_scroll

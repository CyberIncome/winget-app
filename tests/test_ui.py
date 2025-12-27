import pytest
from PySide6.QtWidgets import QTableView, QPlainTextEdit, QPushButton
from src.ui.main_window import MainWindow

def test_main_window_components(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    
    # Check for core components
    assert isinstance(window.table, QTableView)
    assert isinstance(window.console, QPlainTextEdit)
    assert window.console.objectName() == "console"
    
    # Check for buttons
    assert isinstance(window.refresh_btn, QPushButton)
    assert isinstance(window.update_selected_btn, QPushButton)
    assert isinstance(window.update_all_btn, QPushButton)
    assert window.update_all_btn.objectName() == "updateAll"

def test_main_window_title(qtbot):
    window = MainWindow()
    assert window.windowTitle() == "WingetGui"

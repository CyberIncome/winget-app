import pytest
from PySide6.QtWidgets import QTableView, QPlainTextEdit, QPushButton
from PySide6.QtCore import Qt
from src.ui.main_window import MainWindow, UpdateModel

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

def test_selection_logic():
    # Test data
    data = [
        {"Name": "App1", "Id": "Id1", "Version": "1.0", "Available": "1.1", "Source": "winget"},
        {"Name": "App2", "Id": "Id2", "Version": "2.0", "Available": "2.1", "Source": "winget"},
    ]
    model = UpdateModel(data)
    
    # Check initial state (column 0 is checkboxes)
    assert model.data(model.index(0, 0), Qt.CheckStateRole) == Qt.Unchecked
    
    # Toggle selection
    model.setData(model.index(0, 0), Qt.Checked, Qt.CheckStateRole)
    assert model.data(model.index(0, 0), Qt.CheckStateRole) == Qt.Checked
    
    # Get selected IDs
    selected = model.get_selected_ids()
    assert selected == ["Id1"]

def test_main_window_title(qtbot):
    window = MainWindow()
    assert window.windowTitle() == "WingetGui"
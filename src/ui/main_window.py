from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableView, QPlainTextEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WingetGui")
        self.resize(1000, 700)

        # Central Widget & Main Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Top Section: Header
        self.header_label = QLabel("NEON SYSTEM: WINGET UPDATE DASHBOARD")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.header_label)

        # Middle Section: Table
        self.table = QTableView()
        self.main_layout.addWidget(self.table)

        # Bottom Section: Console & Buttons
        self.bottom_layout = QHBoxLayout()
        
        # Console
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setPlaceholderText("SYSTEM LOGS...")
        self.bottom_layout.addWidget(self.console, 2) # Take 2/3 of width

        # Buttons
        self.button_layout = QVBoxLayout()
        
        self.refresh_btn = QPushButton("REFRESH")
        self.button_layout.addWidget(self.refresh_btn)
        
        self.update_selected_btn = QPushButton("UPDATE SELECTED")
        self.button_layout.addWidget(self.update_selected_btn)
        
        self.update_all_btn = QPushButton("UPDATE ALL")
        self.update_all_btn.setObjectName("updateAll")
        self.button_layout.addWidget(self.update_all_btn)
        
        self.bottom_layout.addLayout(self.button_layout, 1) # Take 1/3 of width
        
        self.main_layout.addLayout(self.bottom_layout)
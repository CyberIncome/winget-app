import sys
import os
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QPushButton

def main():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    # Load Styles
    qss_path = os.path.join(os.path.dirname(__file__), "ui", "styles.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r") as f:
            app.setStyleSheet(f.read())

    window = QMainWindow()
    window.setWindowTitle("WingetGui Style Test")
    
    central_widget = QWidget()
    layout = QVBoxLayout(central_widget)
    
    label = QLabel("NEON SYSTEM INITIALIZED")
    layout.addWidget(label)
    
    btn = QPushButton("TEST COMMAND")
    layout.addWidget(btn)
    
    update_btn = QPushButton("UPDATE ALL")
    update_btn.setObjectName("updateAll")
    layout.addWidget(update_btn)
    
    window.setCentralWidget(central_widget)
    window.resize(400, 300)
    
    print("PySide6 with custom styles initialized successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

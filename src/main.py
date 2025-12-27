import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel

def main():
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("WingetGui Smoke Test")
    label = QLabel("WingetGui Environment Ready", window)
    window.setCentralWidget(label)
    window.resize(400, 300)
    # window.show() # Not showing in CI/Automated environment
    print("PySide6 initialized successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

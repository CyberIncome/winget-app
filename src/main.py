import sys
import os
from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow

def main():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    # Load Styles
    qss_path = os.path.join(os.path.dirname(__file__), "ui", "styles.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    
    # Auto-refresh on startup
    window.refresh_updates()
    
    # In CI or if specifically testing, we might not want to exec_()
    if "pytest" not in sys.modules:
        return app.exec()
    return 0

if __name__ == "__main__":
    sys.exit(main())

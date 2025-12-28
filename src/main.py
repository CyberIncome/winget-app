import sys
import os
import logging
from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow

def main():
    # Setup base logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.info("Starting WingetGui...")

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
    
    # In CI or if specifically testing, we might not want to exec_()
    if "pytest" not in sys.modules:
        return app.exec()
    return 0

if __name__ == "__main__":
    sys.exit(main())

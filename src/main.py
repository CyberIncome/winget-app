import sys
import os
import logging
from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.logic.config import CONFIG_DIR

def main():
    # Setup base logging to both terminal and a persistent file in the project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_file = os.path.join(project_root, "winget_gui.log")
    
    from logging.handlers import RotatingFileHandler
    
    # Mode 'a' for append, with rotation to keep it under control
    handler = RotatingFileHandler(
        log_file, 
        maxBytes=10*1024*1024, # 10MB
        backupCount=3,
        encoding="utf-8"
    )
    
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            handler,
            logging.StreamHandler(sys.stdout)
        ]
    )

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

from PySide6.QtWidgets import QMainWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WingetGui")
        self.table = None
        self.console = None
        self.refresh_btn = None
        self.update_selected_btn = None
        self.update_all_btn = None

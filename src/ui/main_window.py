from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableView, QPlainTextEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QProcess
from src.logic.parser import parse_winget_upgrade
from src.logic.executor import WingetExecutor

class UpdateModel(QAbstractTableModel):
    def __init__(self, data=None):
        super().__init__()
        self._data = data or []
        # Selection state: {row_index: bool}
        self._selected = {i: False for i in range(len(self._data))}
        self.headers = ["", "Name", "ID", "Version", "Available", "Source"]

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0: return "" # Checkbox column
            item = self._data[row]
            # Map header to data keys
            key_map = {"Name": "Name", "ID": "Id", "Version": "Version", "Available": "Available", "Source": "Source"}
            key = self.headers[col]
            return item.get(key_map.get(key), "")

        if role == Qt.CheckStateRole and col == 0:
            return Qt.Checked if self._selected.get(row, False) else Qt.Unchecked

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == 0:
            self._selected[index.row()] = (value == Qt.Checked)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True
        return False

    def flags(self, index):
        flags = super().flags(index)
        if index.column() == 0:
            flags |= Qt.ItemIsUserCheckable
        return flags

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None

    def get_selected_ids(self):
        return [self._data[i]["Id"] for i, sel in self._selected.items() if sel]

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WingetGui")
        self.resize(1000, 700)
        
        self.executor = WingetExecutor()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self.current_operation = None # "refresh", "update"
        self.full_output = ""

        self.setup_ui()
        self.connect_signals()
        
    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        self.header_label = QLabel("NEON SYSTEM: WINGET UPDATE DASHBOARD")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.header_label)

        self.table = QTableView()
        self.main_layout.addWidget(self.table)

        self.bottom_layout = QHBoxLayout()
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setPlaceholderText("SYSTEM LOGS...")
        self.bottom_layout.addWidget(self.console, 2)

        self.button_layout = QVBoxLayout()
        self.refresh_btn = QPushButton("REFRESH")
        self.button_layout.addWidget(self.refresh_btn)
        self.update_selected_btn = QPushButton("UPDATE SELECTED")
        self.button_layout.addWidget(self.update_selected_btn)
        self.update_all_btn = QPushButton("UPDATE ALL")
        self.update_all_btn.setObjectName("updateAll")
        self.button_layout.addWidget(self.update_all_btn)
        self.bottom_layout.addLayout(self.button_layout, 1)
        self.main_layout.addLayout(self.bottom_layout)

    def connect_signals(self):
        self.refresh_btn.clicked.connect(self.refresh_updates)
        self.update_selected_btn.clicked.connect(self.update_selected)
        self.update_all_btn.clicked.connect(self.update_all)

    def refresh_updates(self):
        self.current_operation = "refresh"
        self.full_output = ""
        self.log(">>> CHECKING FOR UPDATES...")
        cmd = self.executor.get_check_updates_cmd()
        self.process.start(cmd[0], cmd[1:])

    def update_selected(self):
        model = self.table.model()
        if not model: return
        
        ids = model.get_selected_ids()
        if not ids:
            self.log(">>> NO APPS SELECTED.")
            return

        self.current_operation = "update"
        self.log(f">>> UPDATING {len(ids)} SELECTED APPS...")
        self.process_queue = ids
        self.run_next_update()

    def update_all(self):
        self.current_operation = "update"
        self.log(">>> UPDATING ALL APPS...")
        cmd = self.executor.get_update_all_cmd()
        self.process.start(cmd[0], cmd[1:])

    def run_next_update(self):
        if hasattr(self, "process_queue") and self.process_queue:
            app_id = self.process_queue.pop(0)
            cmd = self.executor.get_update_cmd(app_id)
            self.process.start(cmd[0], cmd[1:])
        else:
            self.log(">>> ALL SELECTED UPDATES COMPLETE.")

    def log(self, message):
        self.console.appendPlainText(message)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.full_output += data
        self.log(data.strip())

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.log(f"ERROR: {data.strip()}")

    def process_finished(self, exit_code, exit_status):
        self.log(f"\nPROCESS FINISHED WITH EXIT CODE {exit_code}")
        
        if self.current_operation == "refresh":
            data = parse_winget_upgrade(self.full_output)
            self.table.setModel(UpdateModel(data))
            self.log(f">>> FOUND {len(data)} UPDATES.")
        
        elif self.current_operation == "update" and hasattr(self, "process_queue") and self.process_queue:
            self.run_next_update()
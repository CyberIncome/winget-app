from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableView, QPlainTextEdit, QPushButton, QLabel, QProgressBar,
    QTabWidget, QHeaderView
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QProcess, Signal, Slot
from src.logic.parser import parse_winget_upgrade, parse_winget_show_version, get_total_inventory
from src.logic.executor import WingetExecutor
import re
import logging

class ConsoleLogHandler(logging.Handler):
    def __init__(self, log_signal):
        super().__init__()
        self.log_signal = log_signal

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_signal.emit(msg)
        except RuntimeError: pass

class UpdateModel(QAbstractTableModel):
    def __init__(self, data=None, is_inventory=False):
        super().__init__()
        self._data = data or []
        self._is_inventory = is_inventory
        self._selected = {i: False for i in range(len(self._data))}
        if is_inventory:
            self.headers = ["", "Name", "Version", "Type", "Managed"]
        else:
            self.headers = ["", "Name", "ID", "Version", "Available"]

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        row, col = index.row(), index.column()

        if role == Qt.DisplayRole:
            if col == 0: return "" 
            item = self._data[row]
            if self._is_inventory:
                keys = ["", "Name", "Version", "Type", "Managed"]
                return item.get(keys[col], "")
            else:
                key_map = {"Name": "Name", "ID": "Id", "Version": "Version", "Available": "Available"}
                return item.get(key_map.get(self.headers[col]), "")

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
        if index.column() == 0: flags |= Qt.ItemIsUserCheckable
        return flags

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None

    def get_selected_ids(self):
        id_key = "Id" if not self._is_inventory else "Name" # For inventory, we might use Name for detail list
        return [self._data[i].get(id_key, self._data[i]["Name"]) for i, sel in self._selected.items() if sel]

class MainWindow(QMainWindow):
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WingetGui")
        self.resize(1200, 800)
        
        self.logger = logging.getLogger(__name__)
        self.executor = WingetExecutor()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self.current_operation = None
        self.full_output = ""
        self.unknown_queue = []

        self.setup_ui()
        self._log_handler = self.setup_logging()
        self.connect_signals()
        self.logger.info("Application initialized.")

    def setup_logging(self):
        handler = ConsoleLogHandler(self.log_signal)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        self.log_signal.connect(self.append_log)
        return handler

    def closeEvent(self, event):
        if hasattr(self, "_log_handler"): logging.getLogger().removeHandler(self._log_handler)
        super().closeEvent(event)

    @Slot(str)
    def append_log(self, message):
        self.console.appendPlainText(message)

    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self.header_label = QLabel("Winget Universal Dashboard")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.header_label)

        # Tab Widget
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Tab 1: Updates
        self.update_tab = QWidget()
        self.update_layout = QHBoxLayout(self.update_tab)
        self.table = QTableView()
        self.setup_table(self.table)
        self.update_layout.addWidget(self.table, 3)
        self.tabs.addTab(self.update_tab, "Updates Available")

        # Tab 2: Total Inventory
        self.inventory_tab = QWidget()
        self.inventory_layout = QHBoxLayout(self.inventory_tab)
        self.inventory_table = QTableView()
        self.setup_table(self.inventory_table)
        self.inventory_layout.addWidget(self.inventory_table, 3)
        self.tabs.addTab(self.inventory_tab, "Total System Inventory")

        # Shared Details Panel (Persistent on right)
        self.details_panel = QPlainTextEdit()
        self.details_panel.setReadOnly(True)
        self.details_panel.setPlaceholderText("Staged apps...")
        self.details_panel.setObjectName("detailsPanel")
        self.details_panel.setFixedWidth(250)
        
        # We need a way to show it next to the tabs
        # I'll wrap the tabs and details in a horizontal layout
        self.tab_and_details = QHBoxLayout()
        # Remove tabs from main_layout and add to this
        self.main_layout.removeWidget(self.tabs)
        self.tab_and_details.addWidget(self.tabs, 4)
        self.tab_and_details.addWidget(self.details_panel, 1)
        self.main_layout.addLayout(self.tab_and_details)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.main_layout.addWidget(self.progress_bar)

        # Bottom Section
        self.bottom_layout = QHBoxLayout()
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.bottom_layout.addWidget(self.console, 2)

        self.button_layout = QVBoxLayout()
        self.refresh_btn = QPushButton("Refresh Updates")
        self.button_layout.addWidget(self.refresh_btn)
        
        self.scan_inventory_btn = QPushButton("Scan Total Inventory")
        self.button_layout.addWidget(self.scan_inventory_btn)
        
        self.update_selected_btn = QPushButton("Update Selected")
        self.button_layout.addWidget(self.update_selected_btn)
        
        self.update_all_btn = QPushButton("Update All")
        self.update_all_btn.setObjectName("updateAll")
        self.button_layout.addWidget(self.update_all_btn)
        self.bottom_layout.addLayout(self.button_layout, 1)
        self.main_layout.addLayout(self.bottom_layout)

    def setup_table(self, table):
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.setGridStyle(Qt.SolidLine) 
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QTableView.SelectRows)
        table.setSelectionMode(QTableView.ExtendedSelection)

    def connect_signals(self):
        self.refresh_btn.clicked.connect(self.refresh_updates)
        self.scan_inventory_btn.clicked.connect(self.refresh_inventory)
        self.update_selected_btn.clicked.connect(self.update_selected)
        self.update_all_btn.clicked.connect(self.update_all)
        self.table.clicked.connect(self.sync_selection_to_checkboxes)
        self.inventory_table.clicked.connect(self.sync_selection_to_checkboxes)

    def sync_selection_to_checkboxes(self):
        # Determine which table is active
        table = self.table if self.tabs.currentIndex() == 0 else self.inventory_table
        model = table.model()
        if not model: return
        
        selected_rows = table.selectionModel().selectedRows()
        for i in range(model.rowCount()): model._selected[i] = False
        for index in selected_rows: model._selected[index.row()] = True
        model.layoutChanged.emit()
        self.update_details_list(model)

    def update_details_list(self, model):
        selected_names = [model._data[i]["Name"] for i, sel in model._selected.items() if sel]
        if selected_names:
            text = "Staged for Action:\n" + "─" * 20 + "\n"
            text += "\n".join(selected_names)
            self.details_panel.setPlainText(text)
        else: self.details_panel.setPlainText("")

    def refresh_updates(self):
        self.tabs.setCurrentIndex(0)
        self.current_operation = "refresh"
        self.full_output = ""
        self.logger.info("Scanning for updates...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.process.start("winget", self.executor.get_check_updates_cmd()[1:])

    def refresh_inventory(self):
        self.tabs.setCurrentIndex(1)
        self.logger.info("Building Total System Inventory (Registry + Shortcuts)...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        # This is a synchronous call currently, we'll keep it simple for now
        data = get_total_inventory()
        self.inventory_table.setModel(UpdateModel(data, is_inventory=True))
        self.inventory_table.resizeColumnsToContents()
        self.logger.info(f"Inventory complete. Found {len(data)} applications.")
        self.progress_bar.setVisible(False)

    def update_selected(self):
        table = self.table if self.tabs.currentIndex() == 0 else self.inventory_table
        model = table.model()
        if not model: return
        
        ids = model.get_selected_ids()
        if not ids:
            self.logger.warning("Nothing selected.")
            return

        self.current_operation = "update"
        self.logger.info(f"Updating {len(ids)} apps...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.process_queue = ids
        self.run_next_update()

    def update_all(self):
        self.tabs.setCurrentIndex(0)
        self.current_operation = "update"
        self.logger.info("Updating all...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.process.start("winget", self.executor.get_update_all_cmd()[1:])

    def run_next_update(self):
        if hasattr(self, "process_queue") and self.process_queue:
            app_id = self.process_queue.pop(0)
            self.logger.info(f"Updating: {app_id}")
            cmd = self.executor.get_update_cmd(app_id)
            self.process.start(cmd[0], cmd[1:])
        else:
            self.logger.info("Updates complete.")
            self.progress_bar.setVisible(False)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.full_output += data
        self.append_log(data.strip())
        match = re.search(r"(\d+)%", data)
        if match:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(match.group(1)))

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.logger.error(f"Error: {data.strip()}")

    def process_finished(self, exit_code, exit_status):
        if self.current_operation == "refresh":
            data = parse_winget_upgrade(self.full_output)
            self.table.setModel(UpdateModel(data))
            self.table.resizeColumnsToContents()
            self.investigate_unknowns(data)
        elif self.current_operation == "investigate":
            self.process_investigation_result()
        elif self.current_operation == "update" and hasattr(self, "process_queue") and self.process_queue:
            self.run_next_update()
        else: self.progress_bar.setVisible(False)

    def investigate_unknowns(self, data):
        self.unknown_queue = [item for item in data if item["Version"].lower() == "unknown"]
        if self.unknown_queue:
            self.current_operation = "investigate"
            self.progress_bar.setRange(0, len(self.unknown_queue))
            self.progress_bar.setValue(0)
            self.run_next_investigation()
        else: self.progress_bar.setVisible(False)

    def run_next_investigation(self):
        if self.unknown_queue:
            item = self.unknown_queue[0]
            self.full_output = ""
            self.process.start("winget", ["show", item["Id"]])
        else:
            self.current_operation = None
            self.progress_bar.setVisible(False)

    def process_investigation_result(self):
        if not self.unknown_queue: return
        item = self.unknown_queue.pop(0)
        v = parse_winget_show_version(self.full_output)
        if v:
            model = self.table.model()
            for d in model._data:
                if d["Id"] == item["Id"]: d["Version"] = v; break
            model.layoutChanged.emit()
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        self.run_next_investigation()

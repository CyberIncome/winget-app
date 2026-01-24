from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableView, QPlainTextEdit, QPushButton, QLabel, QProgressBar,
    QTabWidget, QHeaderView
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QProcess, Signal, Slot, QSortFilterProxyModel, QTimer
from src.logic.parser import parse_winget_upgrade, parse_winget_show_version, get_total_inventory, check_remote_version, get_registry_data
from src.logic.executor import WingetExecutor
import re
import sys
import time
import logging
import threading

# Define a custom logging handler that signals the UI
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
            self.headers = ["", "Name", "Version", "Available", "Type", "Managed"]
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
                keys = ["", "Name", "Version", "Available", "Type", "Managed"]
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
        id_key = "Id" if not self._is_inventory else "Name"
        return [self._data[i].get(id_key, self._data[i]["Name"]) for i, sel in self._selected.items() if sel]

    def get_all_ids(self):
        id_key = "Id" if not self._is_inventory else "Name"
        return [item.get(id_key, item.get("Name")) for item in self._data]

class CustomSortProxy(QSortFilterProxyModel):
    """Sorts Unknown versions to the top."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDynamicSortFilter(True)

    def lessThan(self, left, right):
        source = self.sourceModel()
        if not source or not hasattr(source, "_data") or not source._data:
            return super().lessThan(left, right)
        
        try:
            l_row, r_row = left.row(), right.row()
            if l_row >= len(source._data) or r_row >= len(source._data):
                return super().lessThan(left, right)
                
            v_col = 3 if not source._is_inventory else 2
            
            l_ver = str(source._data[l_row].get("Version", "")).lower()
            r_ver = str(source._data[r_row].get("Version", "")).lower()
            
            l_is_unk = "unknown" in l_ver or "???" in l_ver
            r_is_unk = "unknown" in r_ver or "???" in r_ver
            
            if l_is_unk and not r_is_unk:
                return self.sortOrder() == Qt.AscendingOrder
            if not l_is_unk and r_is_unk:
                return self.sortOrder() == Qt.DescendingOrder
        except (IndexError, KeyError): pass
            
        return super().lessThan(left, right)

class MainWindow(QMainWindow):
    log_signal = Signal(str)
    inventory_data_ready = Signal(list)
    winget_data_ready = Signal(list)
    inventory_update_signal = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WingetGui")
        self.resize(1300, 850)
        
        self.logger = logging.getLogger(__name__)
        self.executor = WingetExecutor()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.handle_process_error)

        self.current_operation = None
        self.full_output = ""
        self.unknown_queue = []
        self._cached_reg_data = None
        self._queue_total = 0
        self._process_last_output = None
        self._process_timed_out = False
        self.process_timeout_secs = 180
        self.process_timeout_timer = QTimer(self)
        self.process_timeout_timer.setInterval(5000)
        self.process_timeout_timer.timeout.connect(self.check_process_timeout)

        self.setup_ui()
        self._log_handler = self.setup_logging()
        self.connect_signals()
        
        self.logger.info("UI: Dashboard initialized. Starting background scans...")
        if "pytest" not in sys.modules:
            QTimer.singleShot(100, self.startup_sequence)

    def setup_logging(self):
        handler = ConsoleLogHandler(self.log_signal)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        self.log_signal.connect(self.append_log)
        return handler

    def startup_sequence(self):
        self.refresh_updates()
        self.refresh_inventory()

    def closeEvent(self, event):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
        if self.process_timeout_timer.isActive():
            self.process_timeout_timer.stop()
        if hasattr(self, "_log_handler"):
            logging.getLogger().removeHandler(self._log_handler)
        super().closeEvent(event)

    @Slot(str)
    def append_log(self, message):
        try:
            self.console.appendPlainText(message)
        except RuntimeError:
            pass

    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self.header_label = QLabel("Winget Universal Dashboard")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.header_label)

        self.tabs = QTabWidget()
        
        # Tab 1: Updates
        self.update_tab = QWidget()
        self.update_layout = QVBoxLayout(self.update_tab)
        self.table = QTableView()
        self.proxy_model = CustomSortProxy()
        self.table.setModel(self.proxy_model)
        self.setup_table(self.table)
        self.update_layout.addWidget(self.table)
        self.tabs.addTab(self.update_tab, "Updates Available")

        # Tab 2: Inventory
        self.inventory_tab = QWidget()
        self.inventory_layout = QVBoxLayout(self.inventory_tab)
        self.inventory_table = QTableView()
        self.inventory_proxy = CustomSortProxy()
        self.inventory_table.setModel(self.inventory_proxy)
        self.setup_table(self.inventory_table)
        self.inventory_layout.addWidget(self.inventory_table)
        self.tabs.addTab(self.inventory_tab, "Total System Inventory")

        self.main_layout.addWidget(self.tabs)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.main_layout.addWidget(self.progress_bar)

        self.bottom_layout = QHBoxLayout()
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.bottom_layout.addWidget(self.console, 2)

        self.button_layout = QVBoxLayout()
        self.refresh_btn = QPushButton("Refresh Updates")
        self.button_layout.addWidget(self.refresh_btn)
        self.scan_inventory_btn = QPushButton("Refresh Inventory")
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
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QTableView.SelectRows)
        table.setSelectionMode(QTableView.ExtendedSelection)
        table.setSortingEnabled(True)

    def connect_signals(self):
        self.refresh_btn.clicked.connect(self.refresh_updates)
        self.scan_inventory_btn.clicked.connect(self.refresh_inventory)
        self.update_selected_btn.clicked.connect(self.update_selected)
        self.update_all_btn.clicked.connect(self.update_all)
        
        # Data bridge signals
        self.inventory_data_ready.connect(self.set_inventory_model)
        self.winget_data_ready.connect(self.apply_winget_results)
        self.inventory_update_signal.connect(self.apply_inventory_version)
        
        # Initial connections
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.sync_selection_to_checkboxes(self.table, self.proxy_model)
        )
        self.inventory_table.selectionModel().selectionChanged.connect(
            lambda *_: self.sync_selection_to_checkboxes(self.inventory_table, self.inventory_proxy)
        )

    def sync_selection_to_checkboxes(self, table=None, proxy=None):
        table = table or (self.table if self.tabs.currentIndex() == 0 else self.inventory_table)
        proxy = proxy or (self.proxy_model if self.tabs.currentIndex() == 0 else self.inventory_proxy)
        source_model = proxy.sourceModel()
        if not source_model:
            return

        # Reset selection map to avoid stale or out-of-range keys.
        source_model._selected = {i: False for i in range(source_model.rowCount())}
        selected_rows = table.selectionModel().selectedRows() if table.selectionModel() else []
        for proxy_idx in selected_rows:
            if not proxy_idx.isValid():
                continue
            source_idx = proxy.mapToSource(proxy_idx)
            if not source_idx.isValid():
                continue
            row = source_idx.row()
            if 0 <= row < source_model.rowCount():
                source_model._selected[row] = True

        if source_model.rowCount() > 0:
            top_left = source_model.index(0, 0)
            bottom_right = source_model.index(source_model.rowCount() - 1, 0)
            source_model.dataChanged.emit(top_left, bottom_right, [Qt.CheckStateRole])

    def refresh_updates(self):
        if self.process.state() != QProcess.NotRunning: return
        self.logger.info("Winget: Scanning for updates...")
        self.tabs.setCurrentIndex(0)
        self.current_operation = "refresh"
        self.full_output = ""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.process.start("winget", self.executor.get_check_updates_cmd()[1:])
        self.start_process_watchdog()

    def refresh_inventory(self):
        self.logger.info("Inventory: Starting scan thread...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        def run_scan():
            try:
                if not self._cached_reg_data: self._cached_reg_data = get_registry_data()
                data = get_total_inventory(reg_data=self._cached_reg_data)
                self.inventory_data_ready.emit(data)
            except Exception as e:
                self.logger.error(f"Inventory Thread Error: {e}", exc_info=True)
                self.inventory_data_ready.emit([])

        threading.Thread(target=run_scan, daemon=True, name="InventoryScanner").start()

    @Slot(list)
    def set_inventory_model(self, data):
        self.logger.info(f"UI: Populating inventory with {len(data)} items.")
        model = UpdateModel(data, is_inventory=True)
        self.inventory_proxy.setSourceModel(model)
        self.inventory_proxy.sort(1, Qt.AscendingOrder)
        self.inventory_table.resizeColumnsToContents()
        self.progress_bar.setVisible(False)
        
        # RE-CONNECT Selection Model
        self.inventory_table.selectionModel().selectionChanged.connect(
            lambda *_: self.sync_selection_to_checkboxes(self.inventory_table, self.inventory_proxy)
        )
        threading.Thread(target=self.inventory_detective_worker, args=(data,), daemon=True).start()

    def inventory_detective_worker(self, data):
        self.logger.info("Detective: Checking non-Winget items for update leads...")
        for i, item in enumerate(data):
            url = item.get("URL")
            if "gimp" in item["Name"].lower() and not url: url = "https://www.gimp.org/downloads/"
            if url and ("github.com" in url or "release" in url.lower() or "gimp.org" in url):
                remote_v = check_remote_version(url)
                if remote_v and remote_v != item["Version"]:
                    self.inventory_update_signal.emit(i, remote_v)
        self.logger.info("Detective: Background check finished.")

    @Slot(int, str)
    def apply_inventory_version(self, index, version):
        model = self.inventory_proxy.sourceModel()
        if model and index < len(model._data):
            model._data[index]["Available"] = version
            model.layoutChanged.emit()
            self.logger.info(f"  [HIT] {model._data[index]['Name']}: new version {version}")

    def update_selected(self):
        if self.process.state() != QProcess.NotRunning:
            self.logger.warning("Winget: Operation already in progress.")
            return
        proxy = self.proxy_model if self.tabs.currentIndex() == 0 else self.inventory_proxy
        model = proxy.sourceModel()
        if not model: return
        ids = model.get_selected_ids()
        if not ids:
            self.logger.warning("UI: Select items to update.")
            return
        self.current_operation = "update"
        self.logger.info(f"Updating {len(ids)} applications...")
        self.progress_bar.setVisible(True)
        self._queue_total = len(ids)
        self.progress_bar.setRange(0, self._queue_total)
        self.progress_bar.setValue(0)
        self.process_queue = ids
        self.run_next_update()

    def update_all(self):
        if self.process.state() != QProcess.NotRunning:
            self.logger.warning("Winget: Operation already in progress.")
            return
        proxy = self.proxy_model
        model = proxy.sourceModel()
        if not model or model._is_inventory:
            self.logger.warning("Winget: Refresh updates before using Update All.")
            return
        ids = model.get_all_ids()
        if not ids:
            self.logger.info("Winget: No updates available.")
            return
        self.current_operation = "update"
        self.logger.info(f"Winget: Updating all ({len(ids)}) applications...")
        self.progress_bar.setVisible(True)
        self._queue_total = len(ids)
        self.progress_bar.setRange(0, self._queue_total)
        self.progress_bar.setValue(0)
        self.process_queue = ids
        self.run_next_update()

    def run_next_update(self):
        if hasattr(self, "process_queue") and self.process_queue:
            app_id = self.process_queue.pop(0)
            if app_id.startswith("Portable."):
                self.logger.warning(f"Skip: {app_id} (manual only)")
                self.progress_bar.setValue(min(self.progress_bar.value() + 1, self._queue_total))
                self.run_next_update()
                return
            self.logger.info(f"Winget: Updating {app_id}")
            cmd = self.executor.get_update_cmd(app_id)
            self.process.start(cmd[0], cmd[1:])
            self.start_process_watchdog()
        else:
            self.logger.info("UI: Batch update complete.")
            self.progress_bar.setVisible(False)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode(errors="replace")
        self.full_output += data
        self.append_log(data.strip())
        self._process_last_output = time.monotonic()
        match = re.search(r"(\d+)%", data)
        if match:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(match.group(1)))

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode(errors="replace")
        self._process_last_output = time.monotonic()
        self.logger.error(f"CLI: {data.strip()}")

    def handle_process_error(self, error):
        self.logger.error(f"Winget: Process error {error}")
        self.progress_bar.setVisible(False)

    def process_finished(self, exit_code, exit_status):
        if self.process_timeout_timer.isActive():
            self.process_timeout_timer.stop()
        if self.current_operation == "refresh":
            self.logger.info("Winget: Parsing results...")
            threading.Thread(target=self.background_parse_winget, args=(self.full_output,), daemon=True).start()
        elif self.current_operation == "investigate":
            self.process_investigation_result()
        elif self.current_operation == "update":
            if self._process_timed_out:
                self.logger.warning("Winget: Update timed out; moving to next item.")
                self._process_timed_out = False
            if hasattr(self, "process_queue"):
                completed = self._queue_total - len(self.process_queue)
                self.progress_bar.setValue(max(0, min(completed, self._queue_total)))
            if hasattr(self, "process_queue") and self.process_queue:
                self.run_next_update()
            else:
                self.logger.info("UI: Batch update complete.")
                self.progress_bar.setVisible(False)
        else: self.progress_bar.setVisible(False)

    def background_parse_winget(self, output):
        if not self._cached_reg_data: self._cached_reg_data = get_registry_data()
        data = parse_winget_upgrade(output, reg_data=self._cached_reg_data)
        self.winget_data_ready.emit(data)

    @Slot(list)
    def apply_winget_results(self, data):
        self.proxy_model.setSourceModel(UpdateModel(data))
        self.proxy_model.sort(1, Qt.AscendingOrder)
        self.table.resizeColumnsToContents()
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.sync_selection_to_checkboxes(self.table, self.proxy_model)
        )
        self.logger.info(f"Winget: Found {len(data)} updates.")
        self.investigate_unknowns(data)

    def investigate_unknowns(self, data):
        self.unknown_queue = [item for item in data if item["Version"].lower() == "unknown"]
        if self.unknown_queue:
            self.logger.info(f"Detective: Probing {len(self.unknown_queue)} apps...")
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
            self.start_process_watchdog()
        else:
            self.current_operation = None
            self.progress_bar.setVisible(False)

    def start_process_watchdog(self):
        self._process_last_output = time.monotonic()
        self._process_timed_out = False
        if not self.process_timeout_timer.isActive():
            self.process_timeout_timer.start()

    def check_process_timeout(self):
        if self.process.state() == QProcess.NotRunning or self._process_last_output is None:
            return
        if time.monotonic() - self._process_last_output > self.process_timeout_secs:
            self._process_timed_out = True
            self.logger.warning("Winget: No output detected; cancelling hung process.")
            self.process.kill()

    def process_investigation_result(self):
        if not self.unknown_queue: return
        item = self.unknown_queue.pop(0)
        v = parse_winget_show_version(self.full_output)
        if v:
            model = self.proxy_model.sourceModel()
            for d in model._data:
                if d["Id"] == item["Id"]: d["Version"] = v; break
            model.layoutChanged.emit()
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        self.run_next_investigation()

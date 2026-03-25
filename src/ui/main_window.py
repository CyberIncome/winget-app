from collections import deque
import os
import re
import sys
import time
import logging
import threading
import ctypes
from typing import Optional, Set

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableView, QPlainTextEdit, QPushButton, QLabel,
    QProgressBar, QHeaderView, QFrame,
    QLineEdit, QMenu, QApplication,
    QSplitter, QListWidget, QListWidgetItem, QStackedWidget
)
from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QProcess,
    Signal, Slot, QSortFilterProxyModel, QTimer,
    QItemSelectionModel, QProcessEnvironment,
)
from PySide6.QtGui import QShortcut, QKeySequence
import requests

from src.logic.parser import (
    parse_winget_upgrade, parse_winget_show_version,
    get_total_inventory, check_remote_version,
    get_registry_data,
)
from src.logic.config import ConfigManager
from src.logic.executor import WingetExecutor

# ── Logging bridge ──────────────────────────────────

class ConsoleLogHandler(logging.Handler):
    def __init__(self, log_signal):
        super().__init__()
        self.log_signal = log_signal

    def emit(self, record):
        try:
            self.log_signal.emit(self.format(record))
        except RuntimeError:
            pass

# ── Stat Card Widget ────────────────────────────────

class StatCard(QFrame):
    def __init__(self, icon, title, value="—", object_name="statCard"):
        super().__init__()
        self.setObjectName(object_name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(8)
        icon_lbl = QLabel(icon)
        icon_lbl.setObjectName("statIcon")
        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("statValue")
        top.addWidget(icon_lbl)
        top.addWidget(self.value_label)
        top.addStretch()

        self.title_label = QLabel(title)
        self.title_label.setObjectName("statTitle")

        layout.addLayout(top)
        layout.addWidget(self.title_label)

    def set_value(self, value):
        self.value_label.setText(str(value))

# ── Table Model ─────────────────────────────────────

class UpdateModel(QAbstractTableModel):
    check_toggled = Signal(int, bool)

    def __init__(self, data=None, is_inventory=False):
        super().__init__()
        self._data = data or []
        self._is_inventory = is_inventory
        self._selected = {item.get("Id") or item.get("Name"): False for item in self._data}
        self._syncing = False

        
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
        item = self._data[row]
        
        if role == Qt.DisplayRole:
            if col == 0: return ""
            if not self._is_inventory:
                keys = ["", "Name", "Id", "Version", "Available"]
                return item.get(keys[col], "")
            else:
                keys = ["", "Name", "Version", "Available", "Type", "Managed"]
                return item.get(keys[col], "")
                
        if role == Qt.CheckStateRole and col == 0:
            return Qt.Checked if self._selected.get(item.get("Id") or item.get("Name"), False) else Qt.Unchecked
            
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == 0:
            checked = value in (2, Qt.Checked, getattr(Qt.CheckState, "Checked", 2))
            item = self._data[index.row()]
            self._selected[item.get("Id") or item.get("Name")] = checked
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            self.check_toggled.emit(index.row(), checked)
            return True
        return False

    def flags(self, index):
        f = super().flags(index)
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None

    def get_selected_ids(self):
        return [id_ for id_, sel in self._selected.items() if sel]

    def get_all_ids(self):
        return [item.get("Id") or item.get("Name") for item in self._data]

# ── Sort Proxy ──────────────────────────────────────

class CustomSortProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDynamicSortFilter(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    def lessThan(self, left, right):
        source = self.sourceModel()
        if not source or not hasattr(source, "_data") or not source._data:
            return super().lessThan(left, right)
        try:
            lr, rr = left.row(), right.row()
            if lr >= len(source._data) or rr >= len(source._data):
                return super().lessThan(left, right)
            lv = str(source._data[lr].get("Version", "")).lower()
            rv = str(source._data[rr].get("Version", "")).lower()
            lu = "unknown" in lv or "???" in lv
            ru = "unknown" in rv or "???" in rv
            if lu and not ru: return self.sortOrder() == Qt.AscendingOrder
            if not lu and ru: return self.sortOrder() == Qt.DescendingOrder
        except (IndexError, KeyError): pass
        return super().lessThan(left, right)

# ── Main Window ─────────────────────────────────────

class MainWindow(QMainWindow):
    log_signal = Signal(str)
    inventory_data_ready = Signal(list)
    winget_data_ready = Signal(list)
    inventory_update_signal = Signal(int, str)
    detective_finished = Signal()
    rate_limit_signal = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Winget Universal Dashboard")
        self.resize(1400, 900)

        self.logger = logging.getLogger(__name__)
        self.executor = WingetExecutor()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.handle_process_error)

        self.current_operation: Optional[str] = None
        self.full_output: str = ""
        self._max_output_bytes: int = 5 * 1024 * 1024
        self.unknown_queue: deque = deque()
        self._cached_reg_data: Optional[list] = None
        self._reg_data_lock: threading.Lock = threading.Lock()
        self._queue_total: int = 0
        self._process_last_output: Optional[float] = None
        self._process_timed_out: bool = False
        self.process_timeout_secs: int = 180
        self._last_scan_time: Optional[str] = None
        self._stat_installed: int = 0
        self._stat_updates: int = 0
        self._stat_unknown: int = 0
        self._active_tasks: Set[str] = set()
        self._operation_lock: threading.Lock = threading.Lock()
        self._is_admin = self.check_admin_status()

        self.process_timeout_timer = QTimer(self)
        self.process_timeout_timer.setInterval(5000)
        self.process_timeout_timer.timeout.connect(self.check_process_timeout)

        self.setup_ui()
        self._log_handler = self.setup_logging()
        self.connect_signals()

        self.logger.info("Dashboard initialized. Starting scans...")
        if "pytest" not in sys.modules:
            QTimer.singleShot(500, self.startup_sequence)

    def setup_logging(self):
        handler = ConsoleLogHandler(self.log_signal)
        fmt = logging.Formatter('%(asctime)s  %(levelname)s  %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(fmt)
        logging.getLogger().addHandler(handler)
        self.log_signal.connect(self.append_log)
        return handler

    def check_admin_status(self):
        try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except: return False

    def startup_sequence(self):
        self.refresh_updates()
        self.refresh_inventory()
        self.update_github_api_status()

    def closeEvent(self, event):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000): self.process.kill()
        if self.process_timeout_timer.isActive(): self.process_timeout_timer.stop()
        super().closeEvent(event)

    @Slot(str)
    def append_log(self, message):
        try: self.console.appendPlainText(message)
        except: pass

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(24, 20, 24, 16)
        
        header_left = QVBoxLayout()
        header_left.setSpacing(2)
        title = QLabel("Winget Universal Dashboard")
        title.setObjectName("headerLabel")
        header_left.addWidget(title)
        
        if not self._is_admin:
            self.admin_warning = QLabel("🛡️ NON-ELEVATED")
            self.admin_warning.setObjectName("adminWarning")
            header_left.addWidget(self.admin_warning)

        subtitle = QLabel("Package manager  •  System inventory")
        subtitle.setObjectName("headerSubtitle")
        header_left.addWidget(subtitle)

        self.activity_banner = QWidget()
        self.activity_banner.setObjectName("activityBanner")
        self.activity_banner.setVisible(False)
        ab_layout = QHBoxLayout(self.activity_banner)
        ab_layout.setContentsMargins(0, 4, 0, 0)
        self.activity_status = QLabel("READY")
        self.activity_status.setObjectName("activityStatus")
        self.activity_progress = QLabel("")
        self.activity_progress.setObjectName("activityProgress")
        ab_layout.addWidget(self.activity_status)
        ab_layout.addWidget(self.activity_progress)
        ab_layout.addStretch()
        header_left.addWidget(self.activity_banner)
        
        header_layout.addLayout(header_left)
        header_layout.addStretch()

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("searchBar")
        self.search_bar.setPlaceholderText("Search applications (Ctrl+F)...")
        self.search_bar.setFixedWidth(300)
        header_layout.addWidget(self.search_bar)
        root.addWidget(header_row)

        # Stats
        stats_widget = QWidget()
        stats_row = QHBoxLayout(stats_widget)
        stats_row.setContentsMargins(24, 0, 24, 16)
        self.stat_installed = StatCard("📦", "Installed Apps")
        self.stat_updates = StatCard("🔄", "Updates Available")
        self.stat_unknown = StatCard("⚠", "Unknown Versions")
        self.stat_scan = StatCard("🕐", "Last Scan")
        for card in [self.stat_installed, self.stat_updates, self.stat_unknown, self.stat_scan]:
            stats_row.addWidget(card)
        root.addWidget(stats_widget)

        # Main
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(150)
        self.sidebar.setMaximumWidth(300)
        items = [("🚀  Updates", "Updates"), ("📦  Inventory", "Inventory"), ("⚙️  Settings", "Settings")]
        for icon_text, _ in items:
            item = QListWidgetItem(icon_text)
            self.sidebar.addItem(item)
        splitter.addWidget(self.sidebar)
        splitter.setStretchFactor(0, 0)
        
        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)

        # Page 0: Updates
        self.update_tab = QWidget()
        ul = QVBoxLayout(self.update_tab)
        self.update_splitter = QSplitter(Qt.Horizontal)
        ul.addWidget(self.update_splitter)
        self.table = QTableView()
        self.proxy_model = CustomSortProxy()
        self.table.setModel(self.proxy_model)
        self.setup_table(self.table)
        self.update_splitter.addWidget(self.table)
        self.update_details = QPlainTextEdit("Select an app to view details...")
        self.update_details.setReadOnly(True)
        self.update_splitter.addWidget(self.update_details)
        self.update_splitter.setSizes([1000, 300])
        self.stack.addWidget(self.update_tab)

        # Page 1: Inventory
        self.inventory_tab = QWidget()
        il = QVBoxLayout(self.inventory_tab)
        self.inventory_splitter = QSplitter(Qt.Horizontal)
        il.addWidget(self.inventory_splitter)
        self.inventory_table = QTableView()
        self.inventory_proxy = CustomSortProxy()
        self.inventory_table.setModel(self.inventory_proxy)
        self.setup_table(self.inventory_table)
        self.inventory_splitter.addWidget(self.inventory_table)
        self.inventory_details = QPlainTextEdit("Select an app to view details...")
        self.inventory_details.setReadOnly(True)
        self.inventory_splitter.addWidget(self.inventory_details)
        self.inventory_splitter.setSizes([1000, 300])
        self.stack.addWidget(self.inventory_tab)

        # Page 2: Settings
        self.settings_tab = QWidget()
        sl = QVBoxLayout(self.settings_tab)
        sl.setContentsMargins(24, 24, 24, 24)
        
        self.pat_input = QLineEdit()
        self.pat_input.setPlaceholderText("ghp_...")
        self.pat_input.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.pat_input.setText(ConfigManager().github_pat or "")
        def on_pat_changed(t):
            ConfigManager().set("github_pat", t)
            self.update_github_api_status()
        self.pat_input.textChanged.connect(on_pat_changed)
        sl.addWidget(QLabel("GitHub Personal Access Token (PAT)"))
        sl.addWidget(self.pat_input)
        
        # API Status
        api_group = QWidget()
        api_group.setObjectName("apiStatusGroup")
        al = QVBoxLayout(api_group)
        self.api_status_lbl = QLabel("Checking status...")
        self.api_reset_lbl = QLabel("")
        self.api_refresh_btn = QPushButton("↻  Refresh API Status")
        self.api_refresh_btn.clicked.connect(self.update_github_api_status)
        al.addWidget(QLabel("GitHub API Capacity"))
        al.addWidget(self.api_status_lbl)
        al.addWidget(self.api_reset_lbl)
        al.addWidget(self.api_refresh_btn)
        sl.addWidget(api_group)
        sl.addStretch()
        self.stack.addWidget(self.settings_tab)

        # Bottom
        bw = QWidget()
        bottom = QHBoxLayout(bw)
        bottom.setContentsMargins(24, 16, 24, 16)
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setVisible(False)
        bottom.addWidget(self.console, 4)
        
        btn_col = QVBoxLayout()
        self.refresh_btn = QPushButton("↻  Refresh Updates")
        self.scan_inventory_btn = QPushButton("↻  Refresh Inventory")
        self.update_selected_btn = QPushButton("⬆  Update Selected")
        self.update_selected_btn.setObjectName("updateSelected")
        self.update_all_btn = QPushButton("⬆  Update All")
        self.update_all_btn.setObjectName("updateAll")
        self.toggle_console_btn = QPushButton("▼  Console")
        self.toggle_console_btn.setObjectName("toggleConsole")
        for b in [self.refresh_btn, self.scan_inventory_btn, self.update_selected_btn, self.update_all_btn, self.toggle_console_btn]:
            btn_col.addWidget(b)
        bottom.addLayout(btn_col, 1)
        root.addWidget(bw)

        # Status Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(200)
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.progress_bar)
        self.statusBar().addPermanentWidget(self.status_label)

        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search_bar.setFocus())
        self.sidebar.setCurrentRow(0)

    def setup_table(self, table):
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableView.SelectRows)
        table.setSelectionMode(QTableView.ExtendedSelection)
        table.setSortingEnabled(True)
        table.clicked.connect(lambda idx: self.handle_table_click(table, idx))

    def handle_table_click(self, table, index):
        proxy = table.model()
        pane = self.update_details if table == self.table else self.inventory_details
        self.update_detail_pane(table, proxy, pane)

    def update_detail_pane(self, table, proxy, pane):
        indexes = table.selectionModel().selectedRows()
        if not indexes:
            pane.setPlainText("Select an app to view details...")
            return
        source = proxy.mapToSource(indexes[0])
        model = proxy.sourceModel()
        if not model or source.row() >= len(model._data): return
        item = model._data[source.row()]
        details = f"=== {item.get('Name', 'Unknown')} ===\n\n"
        for k, v in item.items(): details += f"{k}: {v}\n"
        pane.setPlainText(details)

    def set_ui_busy(self, status, busy, task_name="core"):
        if busy: self._active_tasks.add(task_name)
        else: self._active_tasks.discard(task_name)
        
        is_busy = bool(self._active_tasks)
        self.activity_banner.setVisible(is_busy)
        self.progress_bar.setVisible(is_busy)
        self.refresh_btn.setEnabled(not is_busy)
        self.scan_inventory_btn.setEnabled(not is_busy)
        self.update_selected_btn.setEnabled(not is_busy)
        self.update_all_btn.setEnabled(not is_busy)
        
        if is_busy:
            self.activity_status.setText(status.upper())
            self.status_label.setText(status)
            # Use marquee mode (0,0) for indeterminate tasks like scanning
            if task_name in ["refresh", "inventory", "detective"]:
                self.progress_bar.setRange(0, 0)
            else:
                self.progress_bar.setRange(0, 100)
        else:
            self.update_stats()
            self.activity_status.setText("READY")
            self.status_label.setText("Ready")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

    def connect_signals(self):
        self.refresh_btn.clicked.connect(self.refresh_updates)
        self.scan_inventory_btn.clicked.connect(self.refresh_inventory)
        self.update_selected_btn.clicked.connect(self.update_selected)
        self.update_all_btn.clicked.connect(self.update_all)
        self.search_bar.textChanged.connect(self.filter_tables)
        self.inventory_data_ready.connect(self.set_inventory_model)
        self.winget_data_ready.connect(self.apply_winget_results)
        self.inventory_update_signal.connect(self.apply_inventory_version)
        self.detective_finished.connect(lambda: self.set_ui_busy("Detective: Finished.", False, "detective"))
        self.rate_limit_signal.connect(self.display_rate_limit)
        self.toggle_console_btn.clicked.connect(self.toggle_console)

    def handle_native_checkbox(self, table, proxy, source_row, checked):
        # This method is now primarily for updating the model's internal _selected state
        # based on user interaction with the checkbox.
        # The selection model is no longer directly tied to checkboxes.
        pass

    def sync_selection_to_checkboxes(self, table, proxy):
        # This method is no longer needed as selection and checkboxes are decoupled.
        pass

    def toggle_console(self):
        v = not self.console.isVisible()
        self.console.setVisible(v)
        self.toggle_console_btn.setText("▼  Console" if v else "▶  Console")

    def filter_tables(self, text):
        self.proxy_model.setFilterRegularExpression(text)
        self.inventory_proxy.setFilterRegularExpression(text)

    def update_stats(self):
        self.stat_installed.set_value(self._stat_installed)
        self.stat_updates.set_value(self._stat_updates)
        self.stat_unknown.set_value(self._stat_unknown)
        if self._last_scan_time: self.stat_scan.set_value(self._last_scan_time)

    def refresh_updates(self):
        with self._operation_lock:
            if self.process.state() != QProcess.NotRunning: return
            self.set_ui_busy("Scanning for updates...", True, "refresh")
            self.current_operation = "refresh"
            self.full_output = ""
            
            # Prevent winget from truncating output columns
            env = QProcessEnvironment.systemEnvironment()
            env.insert("COLUMNS", "300")
            self.process.setProcessEnvironment(env)
            
            self.process.start("winget", self.executor.get_check_updates_cmd()[1:])
            self.start_process_watchdog()

    def refresh_inventory(self):
        if "inventory" in self._active_tasks: return
        self.set_ui_busy("Scanning system inventory...", True, "inventory")
        threading.Thread(target=self._run_inventory_scan, daemon=True).start()

    def _run_inventory_scan(self):
        try:
            with self._reg_data_lock:
                if not self._cached_reg_data: self._cached_reg_data = get_registry_data()
                rd = self._cached_reg_data
            data = get_total_inventory(reg_data=rd)
            self.inventory_data_ready.emit(data)
        except Exception as e:
            self.logger.error(f"Inventory error: {e}")
            self.inventory_data_ready.emit([])

    @Slot(list)
    def set_inventory_model(self, data):
        model = UpdateModel(data, is_inventory=True)
        model.check_toggled.connect(lambda r, c: self.handle_native_checkbox(self.inventory_table, self.inventory_proxy, r, c))
        self.inventory_proxy.setSourceModel(model)
        self.inventory_table.setSelectionMode(QTableView.ExtendedSelection)
        self.inventory_table.setSelectionBehavior(QTableView.SelectRows)
        self.inventory_table.doubleClicked.connect(lambda: self.update_selected())
        
        h = self.inventory_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        self.inventory_table.setColumnWidth(0, 40)
        
        # Dynamic flow: stretch Name, fit others to contents
        for c in range(1, model.columnCount()):
            col_name = model.headerData(c, Qt.Horizontal)
            if col_name == "Name":
                h.setSectionResizeMode(c, QHeaderView.Stretch)
            else:
                h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        
        self._stat_installed = len(data)
        self._last_scan_time = time.strftime("%H:%M:%S")
        self.set_ui_busy("Scanning system inventory...", False, "inventory")
        
        self.set_ui_busy("Detective: Checking for updates...", True, "detective")
        threading.Thread(target=self.detective_worker, args=(data,), daemon=True).start()

    def detective_worker(self, data):
        for i, item in enumerate(data):
            url = item.get("URL")
            if not url:
                for k, fb in ConfigManager().url_fallbacks.items():
                    if k in item["Name"].lower(): url = fb; break
            if url and ("github.com" in url or "release" in url.lower()):
                rv = check_remote_version(url, item["Version"])
                if rv: self.inventory_update_signal.emit(i, rv)
        self.detective_finished.emit()

    @Slot(int, str)
    def apply_inventory_version(self, index, version):
        model = self.inventory_proxy.sourceModel()
        if model and index < len(model._data):
            item = model._data[index]
            item["Available"] = version
            model.layoutChanged.emit()
            self.inventory_table.resizeColumnsToContents()
            self.add_detected_update(item)

    def add_detected_update(self, item):
        um = self.proxy_model.sourceModel()
        if not um:
            um = UpdateModel([])
            self.proxy_model.setSourceModel(um)
            um.check_toggled.connect(lambda r, c: self.handle_native_checkbox(self.table, self.proxy_model, r, c))

        # Check for duplicates
        for ex in um._data:
            if ex.get("Id") == item.get("Id") or ex.get("Name") == item.get("Name"):
                ex["Available"] = item.get("Available")
                um.layoutChanged.emit()
                return

        um._data.append({"Name": item["Name"], "Id": item.get("Id", ""), "Version": item["Version"], "Available": item.get("Available", "")})
        # When adding a new item, its checkbox should be unchecked by default
        um._selected[item.get("Id") or item.get("Name")] = False
        um.layoutChanged.emit()
        self.table.resizeColumnsToContents()
        self._stat_updates = len(um._data)
        self.update_stats()

    def update_selected(self):
        proxy = self.proxy_model if self.sidebar.currentRow() == 0 else self.inventory_proxy
        table = self.table if self.sidebar.currentRow() == 0 else self.inventory_table
        model = proxy.sourceModel()
        if not model: return
        ids = model.get_selected_ids()
        if not ids:
            # If no checkboxes are selected, fall back to table selection
            sel = proxy.mapSelectionToSource(table.selectionModel().selection()).indexes()
            ids = list(set(model._data[idx.row()].get("Id") or model._data[idx.row()].get("Name") for idx in sel if idx.row() < len(model._data)))
        if ids: self.batch_update(ids)

    def batch_update(self, ids):
        with self._operation_lock:
            if self.process.state() != QProcess.NotRunning: return
            self.set_ui_busy("Updating apps...", True, "update")
            self.current_operation = "update"
            
            # Prevent truncation during update status reads
            env = QProcessEnvironment.systemEnvironment()
            env.insert("COLUMNS", "300")
            self.process.setProcessEnvironment(env)
            
            self._queue_total = len(ids)
            self.process_queue = deque(ids)
            self.run_next_update()

    def update_all(self):
        model = self.proxy_model.sourceModel()
        if model: self.batch_update(model.get_all_ids())

    def run_next_update(self):
        if hasattr(self, "process_queue") and self.process_queue:
            self.current_updating_id = self.process_queue.popleft()
            app_id = self.current_updating_id
            self.logger.info(f"Updating {app_id}...")
            
            try:
                cmd = self.executor.get_update_cmd(app_id)
                self.process.start(cmd[0], cmd[1:])
                self.start_process_watchdog(timeout=600)
                self.activity_progress.setText(f"({self._queue_total - len(self.process_queue)} / {self._queue_total})")
            except Exception as e:
                self.logger.error(f"Failed to start update for {app_id}: {e}")
                # Skip this one and move to next
                QTimer.singleShot(100, self.run_next_update)
        else:
            self.set_ui_busy("Update complete.", False, "update")

    def remove_id_from_model(self, app_id):
        """Surgically remove an item from the updates list."""
        model = self.proxy_model.sourceModel()
        if not model: return
        
        # Normalize comparison ID
        target_id = str(app_id).strip().lower()
        
        for i, item in enumerate(model._data):
            current_id = (item.get("Id") or item.get("Name")).strip().lower()
            if current_id == target_id:
                model.beginRemoveRows(QModelIndex(), i, i)
                model._data.pop(i)
                # Remove from selection state too
                original_key = item.get("Id") or item.get("Name")
                if original_key in model._selected:
                    del model._selected[original_key]
                model.endRemoveRows()
                self._stat_updates = len(model._data)
                self.update_stats()
                break

    def handle_stdout(self):
        try:
            raw = self.process.readAllStandardOutput().data().decode(errors="replace")
            self.full_output += raw
            clean = re.sub(r'[\r\b\x08]', '', raw.strip())
            if clean:
                self.append_log(clean)
                # Update progress bar if percentage found
                m = re.search(r"(\d+)%", clean)
                if m: self.progress_bar.setValue(int(m.group(1)))
        except Exception as e:
            self.logger.debug(f"Error handling stdout: {e}")

    def handle_stderr(self):
        try:
            raw = self.process.readAllStandardError().data().decode(errors="replace")
            if raw:
                self.logger.error(f"CLI Error: {raw.strip()}")
        except Exception as e:
            self.logger.debug(f"Error handling stderr: {e}")

    def handle_process_error(self, error):
        self.logger.error(f"Process error occurred: {error}")

    def process_finished(self, code, status):
        self.process_timeout_timer.stop()
        
        # Reset progress bar for next operation
        self.progress_bar.setValue(0)
        
        if self.current_operation == "refresh":
            threading.Thread(target=self._background_parse_winget, args=(self.full_output,), daemon=True).start()
        elif self.current_operation == "update":
            if code == 0 and hasattr(self, "current_updating_id"):
                self.remove_id_from_model(self.current_updating_id)
            else:
                msg = f"Update failed for {getattr(self, 'current_updating_id', 'unknown')} (Exit code: {code})"
                self.logger.warning(msg)
                self.append_log(f"\n[!] {msg}")
                
            if self.process_queue: 
                # Small delay before next to allow OS to release locks
                QTimer.singleShot(500, self.run_next_update)
            else: 
                self.set_ui_busy("Update complete.", False, "update")

    def _background_parse_winget(self, output):
        with self._reg_data_lock:
            if not self._cached_reg_data: self._cached_reg_data = get_registry_data()
            rd = self._cached_reg_data
        data = parse_winget_upgrade(output, reg_data=rd)
        self.winget_data_ready.emit(data)

    @Slot(list)
    def apply_winget_results(self, data):
        model = UpdateModel(data)
        model.check_toggled.connect(lambda r, c: self.handle_native_checkbox(self.table, self.proxy_model, r, c))
        self.proxy_model.setSourceModel(model)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.doubleClicked.connect(lambda: self.update_selected())
        
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        
        # Dynamic flow: stretch Name, fit others to contents
        for c in range(1, model.columnCount()):
            col_name = model.headerData(c, Qt.Horizontal)
            if col_name == "Name":
                h.setSectionResizeMode(c, QHeaderView.Stretch)
            else:
                h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
            
        self._stat_updates = len(data)
        self._last_scan_time = time.strftime("%H:%M:%S")
        self.set_ui_busy("Scanning for updates...", False, "refresh")

    def start_process_watchdog(self, timeout=180):
        self.process_timeout_secs = timeout
        self._process_last_output = time.monotonic()
        self.process_timeout_timer.start()

    def check_process_timeout(self):
        if self.process.state() == QProcess.NotRunning: return
        if time.monotonic() - (self._process_last_output or 0) > self.process_timeout_secs:
            self.logger.warning("Process hung; killing.")
            self.process.kill()

    def update_github_api_status(self):
        def worker():
            try:
                headers = {
                    'Accept': 'application/vnd.github.v3+json',
                    'Cache-Control': 'no-cache'
                }
                pat = ConfigManager().github_pat
                if pat:
                    headers['Authorization'] = f"Bearer {pat}"
                    self.logger.debug("Rate limit check: using PAT")
                else:
                    self.logger.debug("Rate limit check: no PAT")
                    
                resp = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=5)
                self.logger.debug(f"API Rate Limit Status: {resp.status_code}")
                if resp.status_code == 200:
                    self.rate_limit_signal.emit(resp.json())
                elif resp.status_code == 401:
                    self.log_signal.emit("GitHub API: Unauthorized (Check your PAT)")
                else:
                    self.log_signal.emit(f"GitHub API: Error {resp.status_code}")
            except Exception as e:
                self.logger.debug(f"API Check failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    @Slot(dict)
    def display_rate_limit(self, data):
        core = data.get("resources", {}).get("core", {})
        rem, lim = core.get("remaining", 0), core.get("limit", 0)
        self.api_status_lbl.setText(f"REMAINING: {rem} / {lim}")
        self.api_reset_lbl.setText(f"Resets at {time.strftime('%H:%M:%S', time.localtime(core.get('reset', 0)))}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

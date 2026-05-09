from collections import deque
from queue import Empty
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
from PySide6.QtGui import QShortcut, QKeySequence, QTextCursor
from src.logic.config import ConfigManager
from src.logic.executor import WingetExecutor, is_valid_app_id

# ── Logging bridge ──────────────────────────────────

class GuiConsoleFilter(logging.Filter):
    """Keep GUI logs readable and avoid recursive process echoes."""

    def filter(self, record):
        return not record.name.startswith(("winget.console", "winget.process"))


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
    def __init__(self, icon, title, value="--", object_name="statCard"):
        super().__init__()
        self.setObjectName(object_name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        icon_lbl = QLabel(icon)
        icon_lbl.setObjectName("statBadge")
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
            self.set_checked(index.row(), checked, emit_signal=True)
            return True
        return False

    def set_checked(self, row, checked, emit_signal=False):
        """Set a row checkbox state and optionally emit user-toggle signal."""
        if row < 0 or row >= len(self._data):
            return False
        item = self._data[row]
        key = item.get("Id") or item.get("Name")
        if self._selected.get(key) == checked:
            return False
        self._selected[key] = checked
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole])
        if emit_signal:
            self.check_toggled.emit(row, checked)
        return True

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

    def _package_ref_for_item(self, item):
        package_id = item.get("Id")
        if is_valid_app_id(package_id):
            return {"value": package_id, "match_by": "id"}
        return {"value": item.get("Name", ""), "match_by": "name"}

    def get_selected_packages(self):
        return [
            self._package_ref_for_item(item)
            for item in self._data
            if self._selected.get(item.get("Id") or item.get("Name"), False)
        ]

    def get_all_packages(self):
        return [self._package_ref_for_item(item) for item in self._data]

    def package_refs_for_rows(self, rows):
        refs = []
        seen = set()
        for row in rows:
            if row >= len(self._data):
                continue
            ref = self._package_ref_for_item(self._data[row])
            key = (ref["match_by"], ref["value"].lower())
            if ref["value"] and key not in seen:
                refs.append(ref)
                seen.add(key)
        return refs

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
        self.console_logger = logging.getLogger("winget.console")
        self.process_logger = logging.getLogger("winget.process")
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
        self._process_start_failed: bool = False
        self._log_process_chunks: bool = os.getenv(
            "WUD_LOG_PROCESS_CHUNKS", ""
        ) == "1"
        self._terminal_line_buffer: str = ""
        self._terminal_progress_mode: bool = False
        self._console_live_line_active: bool = False
        self._progress_is_indeterminate: bool = False
        self.process_timeout_secs: int = 180
        self._last_scan_time: Optional[str] = None
        self._stat_installed: int = 0
        self._stat_updates: int = 0
        self._stat_unknown: int = 0
        self._active_tasks: Set[str] = set()
        self._operation_lock: threading.Lock = threading.Lock()
        self._is_admin = self.check_admin_status()
        self._is_closing: bool = False
        self._pat_status_timer: Optional[QTimer] = None

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
        handler.setLevel(logging.INFO)
        handler.addFilter(GuiConsoleFilter())
        fmt = logging.Formatter('%(asctime)s  %(levelname)s  %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(fmt)
        logging.getLogger().addHandler(handler)
        self.log_signal.connect(self.append_log)
        return handler

    def check_admin_status(self):
        try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except: return False

    def startup_sequence(self):
        if self._is_closing:
            return
        self.logger.info("Starting deferred startup tasks.")
        QTimer.singleShot(0, self.refresh_updates)
        QTimer.singleShot(1200, self.refresh_inventory)
        QTimer.singleShot(2200, self.update_github_api_status)

    def closeEvent(self, event):
        self._is_closing = True
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000): self.process.kill()
        if self.process_timeout_timer.isActive():
            self.process_timeout_timer.stop()
        if self._pat_status_timer and self._pat_status_timer.isActive():
            self._pat_status_timer.stop()
        logging.getLogger().removeHandler(self._log_handler)
        super().closeEvent(event)

    @Slot(str)
    def append_log(self, message):
        if self._is_closing:
            return
        try: self.console.appendPlainText(message)
        except: pass

    def _append_console_line(self, message):
        if not message:
            return
        self.console.appendPlainText(message)
        self.console_logger.info(message)
        self._console_live_line_active = False

    def _replace_console_live_line(self, message):
        if not message:
            return
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self._console_live_line_active:
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
        else:
            if self.console.toPlainText():
                self.console.appendPlainText("")
                cursor = self.console.textCursor()
                cursor.movePosition(QTextCursor.End)
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.removeSelectedText()
        cursor.insertText(message)
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()
        self._console_live_line_active = True

    def _show_process_live_line(self, stream_name):
        line = self._sanitize_terminal_line(self._terminal_line_buffer)
        if line:
            self._replace_console_live_line(line)
        self._terminal_line_buffer = ""
        return line

    def _sanitize_terminal_line(self, text):
        text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
        text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
        text = text.strip()
        if text in {"|", "/", "-", "\\"}:
            return ""
        return text

    def _handle_process_output(self, stream_name, raw):
        if not raw:
            return
        if self._log_process_chunks:
            self.process_logger.debug("%s raw: %r", stream_name, raw)

        completed_lines = []
        recent_live_line = ""
        for char in raw:
            if char == "\r":
                self._terminal_progress_mode = True
                recent_live_line = self._show_process_live_line(stream_name)
                continue
            if char == "\b":
                self._terminal_progress_mode = True
                self._terminal_line_buffer = self._terminal_line_buffer[:-1]
                continue
            if char == "\n":
                line = self._sanitize_terminal_line(self._terminal_line_buffer)
                if line:
                    completed_lines.append(line)
                self._terminal_line_buffer = ""
                self._terminal_progress_mode = False
                self._console_live_line_active = False
                continue
            self._terminal_line_buffer += char

        for line in completed_lines:
            self._append_console_line(line)

        live_line = self._sanitize_terminal_line(self._terminal_line_buffer)
        if self._terminal_progress_mode and live_line:
            self._replace_console_live_line(live_line)

        progress_parts = list(completed_lines)
        if live_line:
            progress_parts.append(live_line)
        elif recent_live_line:
            progress_parts.append(recent_live_line)
        progress_source = "\n".join(progress_parts)
        match = re.search(r"(\d+)%", progress_source)
        if match:
            self._set_progress_value(int(match.group(1)))
        elif self.current_operation == "update" and self._terminal_progress_mode:
            self._set_progress_indeterminate(True)

    def _flush_terminal_line(self):
        line = self._sanitize_terminal_line(self._terminal_line_buffer)
        if line:
            if self._console_live_line_active:
                self._replace_console_live_line(line)
                self.console_logger.info(line)
            else:
                self._append_console_line(line)
        self._terminal_line_buffer = ""
        self._terminal_progress_mode = False
        self._console_live_line_active = False

    def _reset_terminal_renderer(self):
        self._terminal_line_buffer = ""
        self._terminal_progress_mode = False
        self._console_live_line_active = False

    def _set_progress_indeterminate(self, enabled):
        if enabled:
            if not self._progress_is_indeterminate:
                self.progress_bar.setRange(0, 0)
                self._progress_is_indeterminate = True
            return
        if self._progress_is_indeterminate:
            self.progress_bar.setRange(0, 100)
            self._progress_is_indeterminate = False

    def _set_progress_value(self, value):
        self._set_progress_indeterminate(False)
        self.progress_bar.setValue(value)

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
            self.admin_warning = QLabel("NON-ELEVATED")
            self.admin_warning.setObjectName("adminWarning")
            header_left.addWidget(self.admin_warning)

        subtitle = QLabel("Package manager / system inventory")
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
        self.search_bar.setFixedWidth(360)
        self.search_bar.setToolTip("Filter updates and inventory by name or ID")
        header_layout.addWidget(self.search_bar)
        root.addWidget(header_row)

        # Stats
        stats_widget = QWidget()
        stats_row = QHBoxLayout(stats_widget)
        stats_row.setContentsMargins(24, 0, 24, 16)
        self.stat_installed = StatCard(
            "APP", "Installed Apps", object_name="statCard"
        )
        self.stat_updates = StatCard(
            "UPD", "Updates Available", object_name="statCardPrimary"
        )
        self.stat_unknown = StatCard(
            "UNK", "Unknown Versions", object_name="statCardWarning"
        )
        self.stat_scan = StatCard(
            "RUN", "Last Scan", object_name="statCardSuccess"
        )
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
        items = ["Updates", "Inventory", "Settings"]
        for label in items:
            item = QListWidgetItem(label)
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
        self.table.doubleClicked.connect(lambda: self.update_selected())
        self.update_splitter.addWidget(self.table)
        self.update_details = QPlainTextEdit("Select an app to view details...")
        self.update_details.setObjectName("detailsPane")
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
        self.inventory_table.doubleClicked.connect(
            lambda: self.update_selected()
        )
        self.inventory_splitter.addWidget(self.inventory_table)
        self.inventory_details = QPlainTextEdit("Select an app to view details...")
        self.inventory_details.setObjectName("detailsPane")
        self.inventory_details.setReadOnly(True)
        self.inventory_splitter.addWidget(self.inventory_details)
        self.inventory_splitter.setSizes([1000, 300])
        self.stack.addWidget(self.inventory_tab)

        # Page 2: Settings
        self.settings_tab = QWidget()
        sl = QVBoxLayout(self.settings_tab)
        sl.setContentsMargins(24, 24, 24, 24)
        
        self.pat_input = QLineEdit()
        self.pat_input.setObjectName("patInput")
        self.pat_input.setPlaceholderText("ghp_...")
        self.pat_input.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        config = ConfigManager()
        self.pat_input.setText(config.github_pat or "")
        self._pat_status_timer = QTimer(self)
        self._pat_status_timer.setSingleShot(True)
        self._pat_status_timer.setInterval(750)
        self._pat_status_timer.timeout.connect(self.update_github_api_status)
        def on_pat_changed(t):
            config.github_pat = t
            self._pat_status_timer.start()
        self.pat_input.textChanged.connect(on_pat_changed)
        pat_label = QLabel("GitHub Personal Access Token (PAT)")
        pat_label.setObjectName("settingsLabel")
        sl.addWidget(pat_label)
        sl.addWidget(self.pat_input)
        
        # API Status
        api_group = QWidget()
        api_group.setObjectName("apiStatusGroup")
        al = QVBoxLayout(api_group)
        al.setContentsMargins(16, 14, 16, 14)
        al.setSpacing(8)
        self.api_status_lbl = QLabel("Checking status...")
        self.api_status_lbl.setObjectName("apiStatusValue")
        self.api_reset_lbl = QLabel("")
        self.api_reset_lbl.setObjectName("apiStatusHint")
        self.api_refresh_btn = QPushButton("Refresh API Status")
        self.api_refresh_btn.clicked.connect(self.update_github_api_status)
        api_label = QLabel("GitHub API Capacity")
        api_label.setObjectName("settingsLabel")
        al.addWidget(api_label)
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
        self.console.setMaximumBlockCount(2000)
        self.console.setVisible(False)
        bottom.addWidget(self.console, 4)
        
        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)
        self.refresh_btn = QPushButton("Refresh Updates")
        self.refresh_btn.setToolTip("Run winget upgrade scan")
        self.scan_inventory_btn = QPushButton("Refresh Inventory")
        self.scan_inventory_btn.setToolTip("Scan installed and portable apps")
        self.update_selected_btn = QPushButton("Update Selected")
        self.update_selected_btn.setToolTip(
            "Update checked rows or selected table rows"
        )
        self.update_selected_btn.setObjectName("updateSelected")
        self.update_all_btn = QPushButton("Update All")
        self.update_all_btn.setToolTip("Update every app currently listed")
        self.update_all_btn.setObjectName("updateAll")
        self.toggle_console_btn = QPushButton("Show Console")
        self.toggle_console_btn.setToolTip("Show or hide command output")
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
        table.selectionModel().selectionChanged.connect(
            lambda selected, deselected: self.sync_selection_to_checkboxes(
                table, table.model()
            )
        )

    def handle_table_click(self, table, index):
        proxy = table.model()
        pane = self.update_details if table == self.table else self.inventory_details
        self.update_detail_pane(table, proxy, pane)
        source = proxy.mapToSource(index)
        model = proxy.sourceModel()
        if model and 0 <= source.row() < len(model._data):
            item = model._data[source.row()]
            self.logger.debug(
                "Selected row in %s: %s (%s)",
                "updates" if table == self.table else "inventory",
                item.get("Name", "Unknown"),
                item.get("Id", ""),
            )

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
            if task_name in ["refresh", "inventory", "detective", "update"]:
                self._set_progress_indeterminate(True)
            else:
                self._set_progress_indeterminate(False)
        else:
            self.update_stats()
            self.activity_status.setText("READY")
            self.status_label.setText("Ready")
            self._set_progress_indeterminate(False)
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
        model = proxy.sourceModel()
        if not model or getattr(model, "_syncing", False):
            return

        proxy_index = proxy.mapFromSource(model.index(source_row, 0))
        if not proxy_index.isValid():
            return

        selection_model = table.selectionModel()
        if not selection_model:
            return

        item = model._data[source_row]
        self.logger.debug(
            "%s checkbox %s: %s (%s)",
            "Checked" if checked else "Unchecked",
            "updates" if table == self.table else "inventory",
            item.get("Name", "Unknown"),
            item.get("Id", ""),
        )

        try:
            model._syncing = True
            command = QItemSelectionModel.Select if checked else QItemSelectionModel.Deselect
            selection_model.select(
                proxy_index,
                command | QItemSelectionModel.Rows,
            )
            self.update_detail_pane(
                table,
                proxy,
                self.update_details if table == self.table else self.inventory_details,
            )
        finally:
            model._syncing = False

    def sync_selection_to_checkboxes(self, table, proxy):
        model = proxy.sourceModel() if proxy else None
        if not model or getattr(model, "_syncing", False):
            return

        selection_model = table.selectionModel()
        if not selection_model:
            return

        selected_rows = {
            proxy.mapToSource(index).row()
            for index in selection_model.selectedRows()
        }
        try:
            model._syncing = True
            changed = []
            for row in range(len(model._data)):
                checked = row in selected_rows
                if model.set_checked(row, checked, emit_signal=False):
                    changed.append(row)
            if changed:
                self.logger.debug(
                    "Synced %s table selection to checkboxes: %s",
                    "updates" if table == self.table else "inventory",
                    changed,
                )
        finally:
            model._syncing = False

    def toggle_console(self):
        v = not self.console.isVisible()
        self.console.setVisible(v)
        self.toggle_console_btn.setText("Hide Console" if v else "Show Console")
        self.logger.info("Console %s.", "shown" if v else "hidden")

    def filter_tables(self, text):
        self.proxy_model.setFilterRegularExpression(text)
        self.inventory_proxy.setFilterRegularExpression(text)
        self.logger.debug("Filter changed: %r", text)

    def update_stats(self):
        self.stat_installed.set_value(self._stat_installed)
        self.stat_updates.set_value(self._stat_updates)
        self.stat_unknown.set_value(self._stat_unknown)
        if self._last_scan_time: self.stat_scan.set_value(self._last_scan_time)

    def refresh_updates(self):
        with self._operation_lock:
            if self.process.state() != QProcess.NotRunning: return
            self.logger.info("User requested update scan.")
            self.set_ui_busy("Scanning for updates...", True, "refresh")
            self.current_operation = "refresh"
            self.full_output = ""
            self._reset_terminal_renderer()
            
            # Prevent winget from truncating output columns
            env = QProcessEnvironment.systemEnvironment()
            env.insert("COLUMNS", "300")
            self.process.setProcessEnvironment(env)
            
            self.process.start("winget", self.executor.get_check_updates_cmd()[1:])
            self.start_process_watchdog()

    def refresh_inventory(self):
        if "inventory" in self._active_tasks: return
        self.logger.info("User requested inventory scan.")
        self.set_ui_busy("Scanning system inventory...", True, "inventory")
        threading.Thread(target=self._run_inventory_scan, daemon=True).start()

    def _run_inventory_scan(self):
        try:
            from src.logic.parser import get_registry_data, get_total_inventory

            with self._reg_data_lock:
                if not self._cached_reg_data: self._cached_reg_data = get_registry_data()
                rd = self._cached_reg_data
            data = get_total_inventory(reg_data=rd)
            if not self._is_closing:
                self.inventory_data_ready.emit(data)
        except Exception as e:
            self.logger.exception("Inventory error: %s", e)
            if not self._is_closing:
                self.inventory_data_ready.emit([])

    @Slot(list)
    def set_inventory_model(self, data):
        if self._is_closing:
            return
        model = UpdateModel(data, is_inventory=True)
        model.check_toggled.connect(lambda r, c: self.handle_native_checkbox(self.inventory_table, self.inventory_proxy, r, c))
        self.inventory_proxy.setSourceModel(model)
        self.inventory_table.setSelectionMode(QTableView.ExtendedSelection)
        self.inventory_table.setSelectionBehavior(QTableView.SelectRows)
        
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
        from multiprocessing import get_context
        from src.logic.parser import detective_scan_worker

        ctx = get_context("spawn")
        result_queue = ctx.Queue()
        worker = ctx.Process(
            target=detective_scan_worker,
            args=(data, ConfigManager().url_fallbacks, result_queue),
        )
        worker.start()

        result = None
        while worker.is_alive() and not self._is_closing:
            try:
                result = result_queue.get(timeout=0.2)
                break
            except Empty:
                continue

        if self._is_closing:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=1)
            return

        worker.join(timeout=1)
        if result is None:
            try:
                result = result_queue.get_nowait()
            except Empty:
                result = None

        if worker.exitcode not in (0, None):
            self.logger.error(
                "Detective subprocess crashed with exit code %s.",
                worker.exitcode,
            )
        elif result and result.get("error"):
            self.logger.error(
                "Detective subprocess error: %s",
                result["error"],
            )
        elif result:
            for index, version in result.get("results", []):
                if not self._is_closing:
                    self.inventory_update_signal.emit(
                        index, version
                    )
        if not self._is_closing:
            self.detective_finished.emit()

    @Slot(int, str)
    def apply_inventory_version(self, index, version):
        if self._is_closing:
            return
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
        refs = model.get_selected_packages()
        if not refs:
            # If no checkboxes are selected, fall back to table selection
            sel = proxy.mapSelectionToSource(table.selectionModel().selection())
            rows = {idx.row() for idx in sel.indexes()}
            refs = model.package_refs_for_rows(rows)
        if refs:
            self.logger.info("User requested update for %d selected app(s).", len(refs))
            self.batch_update(refs)
        else:
            self.logger.info("Update selected clicked with no selected apps.")

    def _normalize_package_ref(self, package_ref):
        if isinstance(package_ref, dict):
            package_ref = dict(package_ref)
            package_ref.setdefault("silent", True)
            return package_ref
        if is_valid_app_id(package_ref):
            return {
                "value": package_ref,
                "match_by": "id",
                "silent": True,
            }
        return {
            "value": str(package_ref),
            "match_by": "name",
            "silent": True,
        }

    def batch_update(self, package_refs):
        package_refs = [
            self._normalize_package_ref(ref)
            for ref in package_refs
            if ref
        ]
        with self._operation_lock:
            if self.process.state() != QProcess.NotRunning: return
            self.logger.info("Starting update batch: %s", package_refs)
            self.set_ui_busy("Updating apps...", True, "update")
            self.current_operation = "update"
            self.full_output = ""
            self._reset_terminal_renderer()
            
            # Prevent truncation during update status reads
            env = QProcessEnvironment.systemEnvironment()
            env.insert("COLUMNS", "300")
            self.process.setProcessEnvironment(env)
            
            self._queue_total = len(package_refs)
            self.process_queue = deque(package_refs)
            self.run_next_update()

    def update_all(self):
        model = self.proxy_model.sourceModel()
        if model:
            self.logger.info("User requested update all.")
            self.batch_update(model.get_all_packages())

    def run_next_update(self):
        if hasattr(self, "process_queue") and self.process_queue:
            self.current_package_ref = self.process_queue.popleft()
            ref_value = self.current_package_ref["value"]
            match_by = self.current_package_ref["match_by"]
            silent = self.current_package_ref.get("silent", True)
            self.logger.info(
                "Updating %s by %s (silent=%s)...",
                ref_value,
                match_by,
                silent,
            )
            
            try:
                cmd = self.executor.get_update_cmd(
                    ref_value, match_by, silent=silent
                )
                self._set_progress_indeterminate(True)
                self.process.start(cmd[0], cmd[1:])
                self.start_process_watchdog(timeout=600)
                self.activity_progress.setText(f"({self._queue_total - len(self.process_queue)} / {self._queue_total})")
            except Exception as e:
                self.logger.error(f"Failed to start update for {ref_value}: {e}")
                # Skip this one and move to next
                QTimer.singleShot(100, self.run_next_update)
        else:
            self.set_ui_busy("Update complete.", False, "update")

    def remove_package_from_model(self, package_ref):
        """Surgically remove an item from the updates list."""
        model = self.proxy_model.sourceModel()
        if not model: return
        
        # Normalize comparison ID
        target = str(package_ref["value"]).strip().lower()
        match_by = package_ref["match_by"]
        
        for i, item in enumerate(model._data):
            current = (
                item.get("Id") if match_by == "id" else item.get("Name")
            )
            current = str(current or "").strip().lower()
            if current == target:
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
            if raw:
                self._process_last_output = time.monotonic()
            self.full_output += raw
            if len(self.full_output) > self._max_output_bytes:
                self.full_output = self.full_output[-self._max_output_bytes:]
            self._handle_process_output("stdout", raw)
        except Exception as e:
            self.logger.debug(f"Error handling stdout: {e}")

    def handle_stderr(self):
        try:
            raw = self.process.readAllStandardError().data().decode(errors="replace")
            if raw:
                self._process_last_output = time.monotonic()
                self._handle_process_output("stderr", raw)
                self.logger.error(f"CLI Error: {raw.strip()}")
        except Exception as e:
            self.logger.debug(f"Error handling stderr: {e}")

    def handle_process_error(self, error):
        failed_to_start = (
            error == QProcess.FailedToStart
            or str(error).endswith("FailedToStart")
        )
        crashed = (
            error == QProcess.Crashed
            or str(error).endswith("Crashed")
        )
        if crashed:
            current = getattr(self, "current_package_ref", {})
            self.logger.warning(
                "winget child process crashed: operation=%s package=%s",
                self.current_operation,
                current.get("value", ""),
            )
            return
        if not failed_to_start:
            self.logger.error(f"Process error occurred: {error}")
            return

        self._process_start_failed = True
        message = (
            "winget could not be started. Confirm App Installer is "
            "installed and the winget app execution alias is enabled."
        )
        self.logger.error(f"Process error occurred: {error}. {message}")
        self.append_log(f"\n[!] {message}")
        self.process_timeout_timer.stop()

        if self.current_operation == "refresh":
            self.set_ui_busy("Scanning for updates...", False, "refresh")
            self.current_operation = None
        elif self.current_operation == "update":
            if getattr(self, "process_queue", None):
                QTimer.singleShot(100, self.run_next_update)
            else:
                self.set_ui_busy("Update failed.", False, "update")
                self.current_operation = None

    def process_finished(self, code, status):
        self.process_timeout_timer.stop()
        if self._process_start_failed:
            self._process_start_failed = False
            return
        if self._is_closing:
            return
        self._flush_terminal_line()
        self.logger.info(
            "Process finished: operation=%s code=%s status=%s",
            self.current_operation,
            code,
            status,
        )
        
        # Reset progress bar for next operation
        self.progress_bar.setValue(0)
        
        if self.current_operation == "refresh":
            threading.Thread(target=self._background_parse_winget, args=(self.full_output,), daemon=True).start()
        elif self.current_operation == "update":
            if code == 0 and hasattr(self, "current_package_ref"):
                self.remove_package_from_model(self.current_package_ref)
            else:
                current = getattr(self, "current_package_ref", {})
                name = current.get("value", "unknown")
                if (
                    current.get("silent", True)
                    and not current.get(
                        "retried_without_silent", False
                    )
                ):
                    retry_ref = dict(current)
                    retry_ref["silent"] = False
                    retry_ref["retried_without_silent"] = True
                    self.process_queue.appendleft(retry_ref)
                    msg = (
                        f"Retrying {name} without --silent "
                        f"after failure."
                    )
                    self.logger.warning(msg)
                    self.append_log(f"\n[!] {msg}")
                else:
                    msg = (
                        f"Update failed for {name} "
                        f"(Exit code: {code})"
                    )
                    self.logger.warning(msg)
                    self.append_log(f"\n[!] {msg}")
                
            if self.process_queue: 
                # Small delay before next to allow OS to release locks
                QTimer.singleShot(500, self.run_next_update)
            else: 
                self.set_ui_busy("Update complete.", False, "update")

    def _background_parse_winget(self, output):
        from src.logic.parser import get_registry_data, parse_winget_upgrade

        with self._reg_data_lock:
            if not self._cached_reg_data: self._cached_reg_data = get_registry_data()
            rd = self._cached_reg_data
        data = parse_winget_upgrade(output, reg_data=rd)
        if not self._is_closing:
            self.winget_data_ready.emit(data)

    @Slot(list)
    def apply_winget_results(self, data):
        if self._is_closing:
            return
        model = UpdateModel(data)
        model.check_toggled.connect(lambda r, c: self.handle_native_checkbox(self.table, self.proxy_model, r, c))
        self.proxy_model.setSourceModel(model)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        
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
            current = getattr(self, "current_package_ref", {})
            self.logger.warning(
                "Process hung; killing. operation=%s package=%s timeout=%ss",
                self.current_operation,
                current.get("value", ""),
                self.process_timeout_secs,
            )
            self.process.kill()

    def update_github_api_status(self):
        def worker():
            try:
                import requests

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
                    if not self._is_closing:
                        self.rate_limit_signal.emit(resp.json())
                elif resp.status_code == 401:
                    if not self._is_closing:
                        self.log_signal.emit("GitHub API: Unauthorized (Check your PAT)")
                else:
                    if not self._is_closing:
                        self.log_signal.emit(f"GitHub API: Error {resp.status_code}")
            except Exception as e:
                self.logger.debug(f"API Check failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    @Slot(dict)
    def display_rate_limit(self, data):
        if self._is_closing:
            return
        core = data.get("resources", {}).get("core", {})
        rem, lim = core.get("remaining", 0), core.get("limit", 0)
        self.api_status_lbl.setText(f"REMAINING: {rem} / {lim}")
        self.api_reset_lbl.setText(f"Resets at {time.strftime('%H:%M:%S', time.localtime(core.get('reset', 0)))}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

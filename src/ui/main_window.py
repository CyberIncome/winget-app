from collections import deque

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableView, QPlainTextEdit, QPushButton, QLabel,
    QProgressBar, QTabWidget, QHeaderView, QFrame,
    QLineEdit, QMenu, QStatusBar, QApplication,
)
from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QProcess,
    Signal, Slot, QSortFilterProxyModel, QTimer,
)
from PySide6.QtGui import QShortcut, QKeySequence

from src.logic.parser import (
    parse_winget_upgrade, parse_winget_show_version,
    get_total_inventory, check_remote_version,
    get_registry_data, URL_FALLBACKS,
)
from src.logic.executor import WingetExecutor

import os
import re
import sys
import time
import logging
import threading


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
    """Dashboard summary card with icon, value, title."""

    def __init__(
        self, icon, title, value="—",
        object_name="statCard",
    ):
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
    def __init__(self, data=None, is_inventory=False):
        super().__init__()
        self._data = data or []
        self._is_inventory = is_inventory
        self._selected = {
            i: False for i in range(len(self._data))
        }
        if is_inventory:
            self.headers = [
                "", "Name", "Version", "Available",
                "Type", "Managed",
            ]
        else:
            self.headers = [
                "", "Name", "ID", "Version", "Available",
            ]

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return ""
            item = self._data[row]
            if self._is_inventory:
                keys = [
                    "", "Name", "Version", "Available",
                    "Type", "Managed",
                ]
                return item.get(keys[col], "")
            else:
                key_map = {
                    "Name": "Name", "ID": "Id",
                    "Version": "Version",
                    "Available": "Available",
                }
                return item.get(
                    key_map.get(self.headers[col]), ""
                )
        if role == Qt.CheckStateRole and col == 0:
            return (
                Qt.Checked
                if self._selected.get(row, False)
                else Qt.Unchecked
            )
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if (
            role == Qt.CheckStateRole
            and index.column() == 0
        ):
            self._selected[index.row()] = (
                value == Qt.Checked
            )
            self.dataChanged.emit(
                index, index, [Qt.CheckStateRole]
            )
            return True
        return False

    def flags(self, index):
        f = super().flags(index)
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def headerData(
        self, section, orientation,
        role=Qt.DisplayRole,
    ):
        if (
            orientation == Qt.Horizontal
            and role == Qt.DisplayRole
        ):
            return self.headers[section]
        return None

    def get_selected_ids(self):
        k = "Id" if not self._is_inventory else "Name"
        return [
            self._data[i].get(k, self._data[i]["Name"])
            for i, sel in self._selected.items() if sel
        ]

    def get_all_ids(self):
        k = "Id" if not self._is_inventory else "Name"
        return [
            item.get(k, item.get("Name"))
            for item in self._data
        ]


# ── Sort Proxy ──────────────────────────────────────

class CustomSortProxy(QSortFilterProxyModel):
    """Sorts Unknown versions to the top."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDynamicSortFilter(True)
        self.setFilterCaseSensitivity(
            Qt.CaseInsensitive
        )
        self.setFilterKeyColumn(-1)

    def lessThan(self, left, right):
        source = self.sourceModel()
        if (
            not source
            or not hasattr(source, "_data")
            or not source._data
        ):
            return super().lessThan(left, right)
        try:
            lr, rr = left.row(), right.row()
            if (
                lr >= len(source._data)
                or rr >= len(source._data)
            ):
                return super().lessThan(left, right)
            lv = str(
                source._data[lr].get("Version", "")
            ).lower()
            rv = str(
                source._data[rr].get("Version", "")
            ).lower()
            lu = "unknown" in lv or "???" in lv
            ru = "unknown" in rv or "???" in rv
            if lu and not ru:
                return (
                    self.sortOrder() == Qt.AscendingOrder
                )
            if not lu and ru:
                return (
                    self.sortOrder() == Qt.DescendingOrder
                )
        except (IndexError, KeyError):
            pass
        return super().lessThan(left, right)


# ── Main Window ─────────────────────────────────────

class MainWindow(QMainWindow):
    log_signal = Signal(str)
    inventory_data_ready = Signal(list)
    winget_data_ready = Signal(list)
    inventory_update_signal = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Winget Universal Dashboard")
        self.resize(1400, 900)

        self.logger = logging.getLogger(__name__)
        self.executor = WingetExecutor()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(
            self.handle_stdout
        )
        self.process.readyReadStandardError.connect(
            self.handle_stderr
        )
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(
            self.handle_process_error
        )

        self.current_operation = None
        self.full_output = ""
        self._max_output_bytes = 5 * 1024 * 1024
        self.unknown_queue = deque()
        self._cached_reg_data = None
        self._reg_data_lock = threading.Lock()
        self._queue_total = 0
        self._process_last_output = None
        self._process_timed_out = False
        self.process_timeout_secs = 180
        self._last_scan_time = None
        self._stat_installed = 0
        self._stat_updates = 0
        self._stat_unknown = 0

        self.process_timeout_timer = QTimer(self)
        self.process_timeout_timer.setInterval(5000)
        self.process_timeout_timer.timeout.connect(
            self.check_process_timeout
        )

        self.setup_ui()
        self._log_handler = self.setup_logging()
        self.connect_signals()

        self.logger.info(
            "Dashboard initialized. Starting scans..."
        )
        if "pytest" not in sys.modules:
            QTimer.singleShot(100, self.startup_sequence)

    # ── Logging ─────────────────────────────────────

    def setup_logging(self):
        handler = ConsoleLogHandler(self.log_signal)
        fmt = logging.Formatter(
            '%(asctime)s  %(levelname)s  %(message)s',
            datefmt='%H:%M:%S',
        )
        handler.setFormatter(fmt)
        logging.getLogger('src').addHandler(handler)
        self.log_signal.connect(self.append_log)
        return handler

    def startup_sequence(self):
        self.refresh_updates()
        self.refresh_inventory()

    def closeEvent(self, event):
        if (
            self.process
            and self.process.state() != QProcess.NotRunning
        ):
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
        if self.process_timeout_timer.isActive():
            self.process_timeout_timer.stop()
        if hasattr(self, "_log_handler"):
            logging.getLogger('src').removeHandler(
                self._log_handler
            )
        super().closeEvent(event)

    @Slot(str)
    def append_log(self, message):
        try:
            self.console.appendPlainText(message)
        except RuntimeError:
            pass

    # ── UI Setup ────────────────────────────────────

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 0)
        root.setSpacing(16)

        # ── Header row ──
        header_row = QHBoxLayout()
        header_left = QVBoxLayout()
        header_left.setSpacing(2)
        title = QLabel("Winget Universal Dashboard")
        title.setObjectName("headerLabel")
        subtitle = QLabel(
            "Package manager  •  System inventory"
        )
        subtitle.setObjectName("headerSubtitle")
        header_left.addWidget(title)
        header_left.addWidget(subtitle)
        header_row.addLayout(header_left)
        header_row.addStretch()

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("searchBar")
        self.search_bar.setPlaceholderText(
            "Search applications..."
        )
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setFixedWidth(300)
        header_row.addWidget(self.search_bar)
        root.addLayout(header_row)

        # ── Stat cards ──
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.stat_installed = StatCard(
            "📦", "Installed Apps", "—",
            "statCardPrimary",
        )
        self.stat_updates = StatCard(
            "🔄", "Updates Available", "—",
            "statCardSuccess",
        )
        self.stat_unknown = StatCard(
            "⚠", "Unknown Versions", "—",
            "statCardWarning",
        )
        self.stat_scan = StatCard(
            "🕐", "Last Scan", "—", "statCard",
        )
        for card in [
            self.stat_installed, self.stat_updates,
            self.stat_unknown, self.stat_scan,
        ]:
            stats_row.addWidget(card)
        root.addLayout(stats_row)

        # ── Tabs ──
        self.tabs = QTabWidget()

        # Tab 1: Updates
        self.update_tab = QWidget()
        ul = QVBoxLayout(self.update_tab)
        ul.setContentsMargins(0, 8, 0, 0)
        self.table = QTableView()
        self.proxy_model = CustomSortProxy()
        self.table.setModel(self.proxy_model)
        self.setup_table(self.table)
        self.table.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(
                pos, self.table, self.proxy_model
            )
        )
        ul.addWidget(self.table)
        self.tabs.addTab(
            self.update_tab, "  Updates Available  "
        )

        # Tab 2: Inventory
        self.inventory_tab = QWidget()
        il = QVBoxLayout(self.inventory_tab)
        il.setContentsMargins(0, 8, 0, 0)
        self.inventory_table = QTableView()
        self.inventory_proxy = CustomSortProxy()
        self.inventory_table.setModel(
            self.inventory_proxy
        )
        self.setup_table(self.inventory_table)
        self.inventory_table.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.inventory_table.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(
                pos, self.inventory_table,
                self.inventory_proxy,
            )
        )
        il.addWidget(self.inventory_table)
        self.tabs.addTab(
            self.inventory_tab,
            "  System Inventory  ",
        )
        root.addWidget(self.tabs, 1)

        # ── Bottom: Console + Buttons ──
        # Console toggle
        toggle_row = QHBoxLayout()
        self.toggle_console_btn = QPushButton(
            "▼  Console"
        )
        self.toggle_console_btn.setObjectName(
            "toggleConsole"
        )
        self.toggle_console_btn.clicked.connect(
            self.toggle_console
        )
        toggle_row.addWidget(self.toggle_console_btn)
        toggle_row.addStretch()
        root.addLayout(toggle_row)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(180)
        self.console.setVisible(False)
        bottom.addWidget(self.console, 3)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)
        self.refresh_btn = QPushButton("↻  Refresh Updates")
        self.scan_inventory_btn = QPushButton(
            "↻  Refresh Inventory"
        )
        self.update_selected_btn = QPushButton(
            "⬆  Update Selected"
        )
        self.update_selected_btn.setObjectName(
            "updateSelected"
        )
        self.update_all_btn = QPushButton(
            "⬆  Update All"
        )
        self.update_all_btn.setObjectName("updateAll")
        for btn in [
            self.refresh_btn, self.scan_inventory_btn,
            self.update_selected_btn, self.update_all_btn,
        ]:
            btn_col.addWidget(btn)
        btn_col.addStretch()
        bottom.addLayout(btn_col, 1)
        root.addLayout(bottom)

        # ── Status Bar ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("Ready")
        sb = self.statusBar()
        sb.addWidget(self.progress_bar)
        sb.addPermanentWidget(self.status_label)

        # ── Keyboard Shortcuts ──
        QShortcut(
            QKeySequence("Ctrl+F"), self,
            activated=lambda: self.search_bar.setFocus(),
        )

    def setup_table(self, table):
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(
            True
        )
        table.setSelectionBehavior(QTableView.SelectRows)
        table.setSelectionMode(
            QTableView.ExtendedSelection
        )
        table.setSortingEnabled(True)

    def connect_signals(self):
        self.refresh_btn.clicked.connect(
            self.refresh_updates
        )
        self.scan_inventory_btn.clicked.connect(
            self.refresh_inventory
        )
        self.update_selected_btn.clicked.connect(
            self.update_selected
        )
        self.update_all_btn.clicked.connect(
            self.update_all
        )
        self.search_bar.textChanged.connect(
            self.filter_tables
        )
        self.inventory_data_ready.connect(
            self.set_inventory_model
        )
        self.winget_data_ready.connect(
            self.apply_winget_results
        )
        self.inventory_update_signal.connect(
            self.apply_inventory_version
        )
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.sync_selection_to_checkboxes(
                self.table, self.proxy_model
            )
        )
        self.inventory_table.selectionModel().selectionChanged.connect(
            lambda *_: self.sync_selection_to_checkboxes(
                self.inventory_table, self.inventory_proxy
            )
        )

    # ── UI Helpers ──────────────────────────────────

    def toggle_console(self):
        vis = self.console.isVisible()
        self.console.setVisible(not vis)
        self.toggle_console_btn.setText(
            "▶  Console" if vis else "▼  Console"
        )

    def filter_tables(self, text):
        self.proxy_model.setFilterRegularExpression(text)
        self.inventory_proxy.setFilterRegularExpression(
            text
        )

    def update_stats(self):
        self.stat_installed.set_value(self._stat_installed)
        self.stat_updates.set_value(self._stat_updates)
        self.stat_unknown.set_value(self._stat_unknown)
        if self._last_scan_time:
            self.stat_scan.set_value(self._last_scan_time)
        parts = []
        if self._last_scan_time:
            parts.append(
                f"Last scan: {self._last_scan_time}"
            )
        parts.append(f"{self._stat_installed} apps")
        if self._stat_updates:
            parts.append(
                f"{self._stat_updates} updates"
            )
        self.status_label.setText("  ·  ".join(parts))

    def show_context_menu(self, position, table, proxy):
        index = table.indexAt(position)
        if not index.isValid():
            return
        source = proxy.mapToSource(index)
        model = proxy.sourceModel()
        if not model or source.row() >= len(model._data):
            return
        item = model._data[source.row()]

        menu = QMenu(self)
        act_update = menu.addAction(
            f"⬆  Update {item.get('Name', '')}"
        )
        menu.addSeparator()
        act_copy = menu.addAction("📋  Copy ID")
        path = item.get("Path")
        act_open = None
        if path and os.path.exists(
            path if os.path.isdir(path)
            else os.path.dirname(path)
        ):
            act_open = menu.addAction(
                "📂  Open Install Location"
            )

        action = menu.exec(table.viewport().mapToGlobal(
            position
        ))
        if action == act_update:
            app_id = item.get("Id", item.get("Name", ""))
            self._start_single_update(app_id)
        elif action == act_copy:
            app_id = item.get("Id", item.get("Name", ""))
            QApplication.clipboard().setText(app_id)
            self.logger.info(f"Copied: {app_id}")
        elif act_open and action == act_open:
            folder = (
                path if os.path.isdir(path)
                else os.path.dirname(path)
            )
            os.startfile(folder)

    def _start_single_update(self, app_id):
        if self.process.state() != QProcess.NotRunning:
            self.logger.warning(
                "Operation already in progress."
            )
            return
        self.current_operation = "update"
        self._queue_total = 1
        self.process_queue = deque([app_id])
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.run_next_update()

    def sync_selection_to_checkboxes(
        self, table=None, proxy=None,
    ):
        table = table or (
            self.table
            if self.tabs.currentIndex() == 0
            else self.inventory_table
        )
        proxy = proxy or (
            self.proxy_model
            if self.tabs.currentIndex() == 0
            else self.inventory_proxy
        )
        source_model = proxy.sourceModel()
        if not source_model:
            return
        source_model._selected = {
            i: False
            for i in range(source_model.rowCount())
        }
        rows = (
            table.selectionModel().selectedRows()
            if table.selectionModel() else []
        )
        for pi in rows:
            if not pi.isValid():
                continue
            si = proxy.mapToSource(pi)
            if si.isValid():
                r = si.row()
                if 0 <= r < source_model.rowCount():
                    source_model._selected[r] = True
        if source_model.rowCount() > 0:
            tl = source_model.index(0, 0)
            br = source_model.index(
                source_model.rowCount() - 1, 0
            )
            source_model.dataChanged.emit(
                tl, br, [Qt.CheckStateRole]
            )

    # ── Data Operations ─────────────────────────────

    def refresh_updates(self):
        if self.process.state() != QProcess.NotRunning:
            return
        self.logger.info("Scanning for updates...")
        self.tabs.setCurrentIndex(0)
        self.current_operation = "refresh"
        self.full_output = ""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.process.start(
            "winget",
            self.executor.get_check_updates_cmd()[1:],
        )
        self.start_process_watchdog()

    def refresh_inventory(self):
        self.logger.info("Starting inventory scan...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        def run_scan():
            try:
                with self._reg_data_lock:
                    if not self._cached_reg_data:
                        self._cached_reg_data = (
                            get_registry_data()
                        )
                    rd = self._cached_reg_data
                data = get_total_inventory(reg_data=rd)
                self.inventory_data_ready.emit(data)
            except Exception as e:
                self.logger.error(
                    f"Inventory error: {e}",
                    exc_info=True,
                )
                self.inventory_data_ready.emit([])

        threading.Thread(
            target=run_scan, daemon=True,
            name="InventoryScanner",
        ).start()

    @Slot(list)
    def set_inventory_model(self, data):
        self.logger.info(
            f"Inventory: {len(data)} items found."
        )
        model = UpdateModel(data, is_inventory=True)
        self.inventory_proxy.setSourceModel(model)
        self.inventory_proxy.sort(1, Qt.AscendingOrder)
        self.inventory_table.resizeColumnsToContents()
        self.progress_bar.setVisible(False)

        self.inventory_table.selectionModel().selectionChanged.connect(
            lambda *_: self.sync_selection_to_checkboxes(
                self.inventory_table,
                self.inventory_proxy,
            )
        )

        self._stat_installed = len(data)
        unknowns = sum(
            1 for d in data
            if str(d.get("Version", "")).lower()
            in ("unknown", "???")
        )
        self._stat_unknown = unknowns
        self._last_scan_time = time.strftime("%H:%M:%S")
        self.update_stats()
        self.tabs.setTabText(
            1, f"  System Inventory ({len(data)})  "
        )

        threading.Thread(
            target=self.inventory_detective_worker,
            args=(data,), daemon=True,
        ).start()

    def inventory_detective_worker(self, data):
        self.logger.info(
            "Detective: Checking for remote updates..."
        )
        for i, item in enumerate(data):
            url = item.get("URL")
            if not url:
                for k, fb in URL_FALLBACKS.items():
                    if k in item["Name"].lower():
                        url = fb
                        break
            if not url:
                continue
            if (
                "github.com" in url
                or "release" in url.lower()
                or url in URL_FALLBACKS.values()
            ):
                self.logger.debug(
                    f"Detective: {item['Name']} → {url}"
                )
                rv = check_remote_version(
                    url,
                    installed_version=item["Version"],
                )
                if rv:
                    self.inventory_update_signal.emit(
                        i, rv
                    )
        self.logger.info("Detective: Finished.")

    @Slot(int, str)
    def apply_inventory_version(self, index, version):
        model = self.inventory_proxy.sourceModel()
        if model and index < len(model._data):
            item = model._data[index]
            item["Available"] = version
            model.layoutChanged.emit()
            self.logger.info(
                f"  ✓ {item['Name']}: {version}"
            )
            self.add_detected_update_to_updates_tab(item)

    def add_detected_update_to_updates_tab(
        self, inv_item,
    ):
        um = self.proxy_model.sourceModel()
        if um is None:
            um = UpdateModel([])
            self.proxy_model.setSourceModel(um)
            self.table.selectionModel().selectionChanged.connect(
                lambda *_: (
                    self.sync_selection_to_checkboxes(
                        self.table, self.proxy_model
                    )
                )
            )
        name_l = inv_item.get("Name", "").lower()
        iid = inv_item.get("Id", "")
        for ex in um._data:
            if (
                ex.get("Name", "").lower() == name_l
                or ex.get("Id", "") == iid
            ):
                ex["Available"] = inv_item.get(
                    "Available", ""
                )
                um.layoutChanged.emit()
                return
        ui = {
            "Name": inv_item.get("Name", ""),
            "Id": inv_item.get("Id", ""),
            "Version": inv_item.get("Version", ""),
            "Available": inv_item.get("Available", ""),
        }
        ni = len(um._data)
        um._data.append(ui)
        um._selected[ni] = False
        um.layoutChanged.emit()
        self._stat_updates = len(um._data)
        self.update_stats()
        self.tabs.setTabText(
            0,
            f"  Updates Available ({len(um._data)})  ",
        )
        self.table.resizeColumnsToContents()

    # ── Update Execution ────────────────────────────

    def update_selected(self):
        if self.process.state() != QProcess.NotRunning:
            self.logger.warning("Already in progress.")
            return
        proxy = (
            self.proxy_model
            if self.tabs.currentIndex() == 0
            else self.inventory_proxy
        )
        model = proxy.sourceModel()
        if not model:
            return
        ids = model.get_selected_ids()
        if not ids:
            self.logger.warning("Select items first.")
            return
        self.current_operation = "update"
        self.logger.info(f"Updating {len(ids)} apps...")
        self.progress_bar.setVisible(True)
        self._queue_total = len(ids)
        self.progress_bar.setRange(0, self._queue_total)
        self.progress_bar.setValue(0)
        self.process_queue = deque(ids)
        self.run_next_update()

    def update_all(self):
        if self.process.state() != QProcess.NotRunning:
            self.logger.warning("Already in progress.")
            return
        model = self.proxy_model.sourceModel()
        if not model or model._is_inventory:
            self.logger.warning(
                "Refresh updates first."
            )
            return
        ids = model.get_all_ids()
        if not ids:
            self.logger.info("No updates available.")
            return
        self.current_operation = "update"
        self.logger.info(f"Updating all {len(ids)}...")
        self.progress_bar.setVisible(True)
        self._queue_total = len(ids)
        self.progress_bar.setRange(0, self._queue_total)
        self.progress_bar.setValue(0)
        self.process_queue = deque(ids)
        self.run_next_update()

    def run_next_update(self):
        while (
            hasattr(self, "process_queue")
            and self.process_queue
        ):
            app_id = self.process_queue.popleft()
            if app_id.startswith("Portable."):
                self.logger.warning(
                    f"Skip: {app_id} (manual)"
                )
                self.progress_bar.setValue(
                    min(
                        self.progress_bar.value() + 1,
                        self._queue_total,
                    )
                )
                continue
            self.logger.info(f"Updating {app_id}...")
            try:
                cmd = self.executor.get_update_cmd(app_id)
            except ValueError as e:
                self.logger.error(f"Bad ID: {e}")
                continue
            self.process.start(cmd[0], cmd[1:])
            self.start_process_watchdog()
            return
        self.logger.info("Batch update complete.")
        self.progress_bar.setVisible(False)

    # ── Process I/O ─────────────────────────────────

    def handle_stdout(self):
        raw = (
            self.process.readAllStandardOutput()
            .data().decode(errors="replace")
        )
        if len(self.full_output) < self._max_output_bytes:
            self.full_output += raw
        self.append_log(raw.strip())
        self._process_last_output = time.monotonic()
        m = re.search(r"(\d+)%", raw)
        if m:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(m.group(1)))

    def handle_stderr(self):
        raw = (
            self.process.readAllStandardError()
            .data().decode(errors="replace")
        )
        self._process_last_output = time.monotonic()
        self.logger.error(f"CLI: {raw.strip()}")

    def handle_process_error(self, error):
        self.logger.error(f"Process error: {error}")
        self.progress_bar.setVisible(False)

    def process_finished(self, exit_code, exit_status):
        if self.process_timeout_timer.isActive():
            self.process_timeout_timer.stop()
        if self.current_operation == "refresh":
            self.logger.info("Parsing results...")
            threading.Thread(
                target=self.background_parse_winget,
                args=(self.full_output,), daemon=True,
            ).start()
        elif self.current_operation == "investigate":
            self.process_investigation_result()
        elif self.current_operation == "update":
            if self._process_timed_out:
                self.logger.warning("Timed out, next...")
                self._process_timed_out = False
            if hasattr(self, "process_queue"):
                done = (
                    self._queue_total
                    - len(self.process_queue)
                )
                self.progress_bar.setValue(
                    max(0, min(done, self._queue_total))
                )
            if (
                hasattr(self, "process_queue")
                and self.process_queue
            ):
                self.run_next_update()
            else:
                self.logger.info("Update complete.")
                self.progress_bar.setVisible(False)
        else:
            self.progress_bar.setVisible(False)

    def background_parse_winget(self, output):
        with self._reg_data_lock:
            if not self._cached_reg_data:
                self._cached_reg_data = (
                    get_registry_data()
                )
            rd = self._cached_reg_data
        data = parse_winget_upgrade(output, reg_data=rd)
        self.winget_data_ready.emit(data)

    @Slot(list)
    def apply_winget_results(self, data):
        self.proxy_model.setSourceModel(UpdateModel(data))
        self.proxy_model.sort(1, Qt.AscendingOrder)
        self.table.resizeColumnsToContents()
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.sync_selection_to_checkboxes(
                self.table, self.proxy_model
            )
        )
        self._stat_updates = len(data)
        self._last_scan_time = time.strftime("%H:%M:%S")
        self.update_stats()
        self.tabs.setTabText(
            0, f"  Updates Available ({len(data)})  "
        )
        self.logger.info(f"Found {len(data)} updates.")
        self.investigate_unknowns(data)

    # ── Unknown Investigation ───────────────────────

    def investigate_unknowns(self, data):
        self.unknown_queue = deque(
            item for item in data
            if item["Version"].lower() == "unknown"
        )
        if self.unknown_queue:
            self.logger.info(
                f"Probing {len(self.unknown_queue)} "
                f"unknown versions..."
            )
            self.current_operation = "investigate"
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(
                0, len(self.unknown_queue)
            )
            self.progress_bar.setValue(0)
            self.run_next_investigation()
        else:
            self.progress_bar.setVisible(False)

    def run_next_investigation(self):
        if self.unknown_queue:
            self.full_output = ""
            self.process.start(
                "winget",
                ["show", self.unknown_queue[0]["Id"]],
            )
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
        if (
            self.process.state() == QProcess.NotRunning
            or self._process_last_output is None
        ):
            return
        if (
            time.monotonic() - self._process_last_output
            > self.process_timeout_secs
        ):
            self._process_timed_out = True
            self.logger.warning(
                "No output; killing hung process."
            )
            self.process.kill()

    def process_investigation_result(self):
        if not self.unknown_queue:
            return
        item = self.unknown_queue.popleft()
        v = parse_winget_show_version(self.full_output)
        if v:
            model = self.proxy_model.sourceModel()
            for d in model._data:
                if d["Id"] == item["Id"]:
                    d["Version"] = v
                    break
            model.layoutChanged.emit()
            self._stat_unknown = max(
                0, self._stat_unknown - 1
            )
            self.update_stats()
        self.progress_bar.setValue(
            self.progress_bar.value() + 1
        )
        self.run_next_investigation()

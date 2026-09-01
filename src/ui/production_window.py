"""Final production window compatibility and safety layer."""

from __future__ import annotations

import time

from PySide6.QtCore import (
    QModelIndex,
    QProcess,
    QProcessEnvironment,
    QTimer,
    Qt,
)
from PySide6.QtWidgets import QHeaderView, QTableView

from src.logic.config import ConfigManager
from src.logic.executor import (
    is_valid_app_id,
    validate_source_name,
)
from src.ui.hardened_window import HardenedMainWindow
from src.ui.main_window import UpdateModel


class ProductionUpdateModel(UpdateModel):
    """Update model with source-aware identity and source display."""

    def __init__(self, data=None, is_inventory=False):
        super().__init__(data=data, is_inventory=is_inventory)
        if not is_inventory:
            self.headers = [
                "",
                "Name",
                "ID",
                "Version",
                "Available",
                "Source",
            ]
            self._selected = {
                self.selection_key_for_item(item): False
                for item in self._data
            }

    def selection_key_for_item(self, item):
        """Return a checkbox identity that distinguishes package sources."""
        base = item.get("Id") or item.get("Name")
        if self._is_inventory:
            return base
        return (base, item.get("Source", ""))

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if (
            not self._is_inventory
            and role == Qt.CheckStateRole
            and index.column() == 0
        ):
            item = self._data[index.row()]
            key = self.selection_key_for_item(item)
            return Qt.Checked if self._selected.get(key, False) else Qt.Unchecked
        if (
            not self._is_inventory
            and role == Qt.DisplayRole
            and index.column() == 5
        ):
            return self._data[index.row()].get("Source", "")
        return super().data(index, role)

    def set_checked(self, row, checked, emit_signal=False):
        """Set a checkbox without merging rows from different sources."""
        if self._is_inventory:
            return super().set_checked(row, checked, emit_signal=emit_signal)
        if row < 0 or row >= len(self._data):
            return False
        item = self._data[row]
        key = self.selection_key_for_item(item)
        if self._selected.get(key) == checked:
            return False
        self._selected[key] = checked
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole])
        if emit_signal:
            self.check_toggled.emit(row, checked)
        return True


class ProductionMainWindow(HardenedMainWindow):
    """Apply final Qt and package-target safety guards."""

    def __init__(self):
        self._failed_start_pending = False
        self._terminal_line_limit = 16 * 1024
        super().__init__()
        self.console.setMaximumBlockCount(10_000)
        self.process.started.connect(self._handle_process_started)
        self.update_all_btn.setToolTip(
            "Update every package proven upgradeable by the current Winget scan"
        )

    # ── Managed job result safety ───────────────────

    def _start_job(
        self,
        name,
        target,
        args=(),
        timeout=180,
        on_success=None,
        on_failure=None,
    ):
        guarded_success = None
        if on_success is not None:
            guarded_success = lambda value: self._dispatch_job_success(
                name,
                value,
                on_success,
                on_failure,
            )
        return super()._start_job(
            name,
            target,
            args=args,
            timeout=timeout,
            on_success=guarded_success,
            on_failure=on_failure,
        )

    def _dispatch_job_success(
        self,
        name,
        value,
        callback,
        failure_callback=None,
    ):
        """Convert result-handling exceptions into explicit job failures."""
        if self._is_closing:
            return
        try:
            callback(value)
        except Exception as exc:
            message = f"{name} result handling failed: {exc}"
            self.logger.exception(message)
            self._handle_job_failure(
                name,
                message,
                failure_callback,
            )

    def _handle_job_failure(self, name, message, callback=None):
        """Run failure recovery without allowing its callback to wedge state."""
        if self._is_closing:
            return
        self.logger.error("Background job failed: %s", message)
        self.append_log(f"\n[!] {message}")
        if callback is None:
            return
        try:
            callback(message)
        except Exception as exc:
            self.logger.exception(
                "Failure recovery callback crashed for %s: %s",
                name,
                exc,
            )
            self.append_log(
                f"\n[!] Failure recovery for {name} also failed: {exc}"
            )

    # ── Process output bounds ───────────────────────

    def _handle_process_output(self, stream_name, raw):
        """Render process output while bounding a never-terminated live line."""
        if raw:
            last_break = max(raw.rfind("\n"), raw.rfind("\r"))
            if last_break < 0:
                combined = self._terminal_line_buffer + raw
                if len(combined) > self._terminal_line_limit:
                    self._terminal_line_buffer = ""
                    raw = combined[-self._terminal_line_limit :]
            else:
                tail = raw[last_break + 1 :]
                if len(tail) > self._terminal_line_limit:
                    raw = (
                        raw[: last_break + 1]
                        + tail[-self._terminal_line_limit :]
                    )

        super()._handle_process_output(stream_name, raw)
        if len(self._terminal_line_buffer) > self._terminal_line_limit:
            self._terminal_line_buffer = self._terminal_line_buffer[
                -self._terminal_line_limit :
            ]

    # ── QProcess generation safety ──────────────────

    def handle_process_error(self, error):
        failed_to_start = (
            error == QProcess.FailedToStart
            or str(error).endswith("FailedToStart")
        )
        if failed_to_start:
            self._failed_start_pending = True
            # A missing/broken Winget executable is process-global, not a
            # package-specific failure. Abort the remaining batch instead of
            # attempting the same impossible start for every queued package.
            if self.current_operation == "update" and hasattr(
                self, "process_queue"
            ):
                self.process_queue.clear()
                self.activity_progress.setText("")
        super().handle_process_error(error)

    def _handle_process_started(self):
        self._failed_start_pending = False
        self._process_start_failed = False

    def process_finished(self, code, status):
        if self._failed_start_pending:
            self.logger.warning(
                "Ignoring finished signal for a failed-to-start generation."
            )
            self._failed_start_pending = False
            self._process_start_failed = False
            return
        super().process_finished(code, status)

    # ── Winget update-model contract ────────────────

    def apply_winget_results(self, data):
        """Display source metadata and tag rows proven upgradeable by Winget."""
        if self._is_closing:
            return
        tagged = []
        for item in data or []:
            row = dict(item)
            row["UpdateSource"] = "winget"
            tagged.append(row)

        model = ProductionUpdateModel(tagged)
        model.check_toggled.connect(
            lambda row, checked: self.handle_native_checkbox(
                self.table,
                self.proxy_model,
                row,
                checked,
            )
        )
        self.proxy_model.setSourceModel(model)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setSelectionBehavior(QTableView.SelectRows)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        for column in range(1, model.columnCount()):
            column_name = model.headerData(column, Qt.Horizontal)
            mode = (
                QHeaderView.Stretch
                if column_name == "Name"
                else QHeaderView.ResizeToContents
            )
            header.setSectionResizeMode(column, mode)

        self._stat_updates = len(tagged)
        self._last_scan_time = time.strftime("%H:%M:%S")
        self.set_ui_busy(
            "Scanning for updates...", False, "refresh"
        )

    def _ensure_production_update_model(self):
        """Ensure detective-only results still use the production table contract."""
        model = self.proxy_model.sourceModel()
        if model is not None:
            return model
        model = ProductionUpdateModel([])
        model.check_toggled.connect(
            lambda row, checked: self.handle_native_checkbox(
                self.table,
                self.proxy_model,
                row,
                checked,
            )
        )
        self.proxy_model.setSourceModel(model)
        return model

    def _detective_job_succeeded(self, results):
        """Merge detective data without overriding authoritative Winget rows."""
        model = self._ensure_production_update_model()
        existing_objects = {id(item) for item in model._data}
        official_available = {
            id(item): item.get("Available", "")
            for item in model._data
            if self._is_winget_update_item(item)
        }

        super()._detective_job_succeeded(results)
        model = self.proxy_model.sourceModel()
        if model is None:
            return

        restored = False
        for item in model._data:
            item_id = id(item)
            if item_id in official_available:
                official = official_available[item_id]
                if item.get("Available", "") != official:
                    item["Available"] = official
                    restored = True
            elif item_id not in existing_objects:
                legacy_key = item.get("Id") or item.get("Name")
                model._selected.pop(legacy_key, None)
                item["UpdateSource"] = "detective"
                item.setdefault("Source", "detective")
                model._selected[model.selection_key_for_item(item)] = False
        if restored:
            model.layoutChanged.emit()

    @staticmethod
    def _package_ref_for_winget_item(item):
        try:
            source = validate_source_name(item.get("Source"))
        except ValueError:
            return None

        package_id = item.get("Id")
        if is_valid_app_id(package_id):
            ref = {"value": package_id, "match_by": "id"}
        else:
            name = str(item.get("Name") or "").strip()
            if not name or name.startswith("-"):
                return None
            ref = {"value": name, "match_by": "name"}
        if source:
            ref["source"] = source
        return ref

    @staticmethod
    def _is_winget_update_item(item):
        return item.get("UpdateSource") == "winget"

    @staticmethod
    def _package_ref_key(ref):
        return (
            ref["match_by"],
            ref["value"].lower(),
            str(ref.get("source") or "").lower(),
        )

    @staticmethod
    def _selection_key(model, item):
        if hasattr(model, "selection_key_for_item"):
            return model.selection_key_for_item(item)
        return item.get("Id") or item.get("Name")

    def _selected_source_items(self, table, proxy):
        model = proxy.sourceModel() if proxy else None
        if model is None:
            return []

        checked = [
            item
            for item in model._data
            if model._selected.get(
                self._selection_key(model, item), False
            )
        ]
        if checked:
            return checked

        selection_model = table.selectionModel()
        if selection_model is None:
            return []
        selection = proxy.mapSelectionToSource(
            selection_model.selection()
        )
        rows = sorted({index.row() for index in selection.indexes()})
        return [
            model._data[row]
            for row in rows
            if 0 <= row < len(model._data)
        ]

    def _winget_refs_for_inventory_items(self, inventory_items):
        """Map registry inventory names to unique authoritative Winget rows."""
        update_model = self.proxy_model.sourceModel()
        if update_model is None:
            return []

        # Registry uninstall subkeys are local inventory identifiers, not
        # Winget package provenance. Never use them to select a Winget row.
        by_name = {}
        for update_item in update_model._data:
            if not self._is_winget_update_item(update_item):
                continue
            name = str(update_item.get("Name") or "").strip().lower()
            if name:
                by_name.setdefault(name, []).append(update_item)

        refs = []
        seen = set()
        for inventory_item in inventory_items:
            name = str(
                inventory_item.get("Name") or ""
            ).strip().lower()
            candidates = by_name.get(name, []) if name else []
            if len(candidates) != 1:
                continue

            ref = self._package_ref_for_winget_item(candidates[0])
            if ref is None:
                continue
            key = self._package_ref_key(ref)
            if key not in seen:
                refs.append(ref)
                seen.add(key)
        return refs

    def update_selected(self):
        """Update only selections backed by a current Winget upgrade row."""
        on_updates = self.sidebar.currentRow() == 0
        proxy = self.proxy_model if on_updates else self.inventory_proxy
        table = self.table if on_updates else self.inventory_table
        selected_items = self._selected_source_items(table, proxy)
        if not selected_items:
            self.logger.info(
                "Update selected clicked with no selected apps."
            )
            return

        if on_updates:
            refs = []
            seen = set()
            for item in selected_items:
                if not self._is_winget_update_item(item):
                    continue
                ref = self._package_ref_for_winget_item(item)
                if ref is None:
                    continue
                key = self._package_ref_key(ref)
                if key not in seen:
                    refs.append(ref)
                    seen.add(key)
        else:
            refs = self._winget_refs_for_inventory_items(selected_items)

        if refs:
            self.logger.info(
                "User requested update for %d Winget-proven app(s).",
                len(refs),
            )
            self.batch_update(refs)
            return

        message = (
            "Selected app(s) are not present in the current Winget upgrade "
            "scan; no update command was run."
        )
        self.logger.warning(message)
        self.append_log(f"\n[!] {message}")

    def update_all(self):
        """Update all current Winget scan rows, excluding detective-only hits."""
        model = self.proxy_model.sourceModel()
        if model is None:
            return
        refs = []
        seen = set()
        for item in model._data:
            if not self._is_winget_update_item(item):
                continue
            ref = self._package_ref_for_winget_item(item)
            if ref is None:
                continue
            key = self._package_ref_key(ref)
            if key not in seen:
                refs.append(ref)
                seen.add(key)
        if refs:
            self.logger.info(
                "User requested update all for %d Winget-proven app(s).",
                len(refs),
            )
            self.batch_update(refs)

    def run_next_update(self):
        """Run the next queued exact package/source update."""
        if self._is_closing:
            return
        if hasattr(self, "process_queue") and self.process_queue:
            self.current_package_ref = self.process_queue.popleft()
            ref_value = self.current_package_ref["value"]
            match_by = self.current_package_ref["match_by"]
            source = self.current_package_ref.get("source")
            silent = self.current_package_ref.get("silent", True)
            self.logger.info(
                "Updating %s by %s source=%s (silent=%s)...",
                ref_value,
                match_by,
                source or "default",
                silent,
            )
            try:
                command = self.executor.get_update_cmd(
                    ref_value,
                    match_by,
                    silent=silent,
                    source=source,
                )
                environment = QProcessEnvironment.systemEnvironment()
                environment.insert("COLUMNS", "300")
                self.process.setProcessEnvironment(environment)
                self._set_progress_indeterminate(True)
                self.process.start(command[0], command[1:])
                self.start_process_watchdog(
                    timeout=1800,
                    idle_warning=300,
                )
                current = self._queue_total - len(self.process_queue)
                self.activity_progress.setText(
                    f"({current} / {self._queue_total})"
                )
            except Exception as exc:
                self.logger.exception(
                    "Failed to start update for %s", ref_value
                )
                self.append_log(
                    f"\n[!] Failed to start {ref_value}: {exc}"
                )
                QTimer.singleShot(100, self.run_next_update)
            return

        self.current_operation = None
        self.activity_progress.setText("")
        self.set_ui_busy("Update complete.", False, "update")

    def remove_package_from_model(self, package_ref):
        """Remove only the package row matching reference and source."""
        model = self.proxy_model.sourceModel()
        if model is None:
            return
        target = str(package_ref["value"]).strip().lower()
        match_by = package_ref["match_by"]
        target_source = str(package_ref.get("source") or "").strip().lower()

        for row_index, item in enumerate(model._data):
            current = (
                item.get("Id") if match_by == "id" else item.get("Name")
            )
            current = str(current or "").strip().lower()
            item_source = str(item.get("Source") or "").strip().lower()
            if current != target:
                continue
            if target_source and item_source != target_source:
                continue

            selection_key = self._selection_key(model, item)
            model.beginRemoveRows(QModelIndex(), row_index, row_index)
            model._data.pop(row_index)
            model._selected.pop(selection_key, None)
            model.endRemoveRows()
            self._stat_updates = len(model._data)
            self.update_stats()
            return

    # ── Shutdown persistence ─────────────────────────

    def closeEvent(self, event):
        if (
            not self._is_closing
            and hasattr(self, "_pat_save_timer")
            and self._pat_save_timer.isActive()
        ):
            self._pat_save_timer.stop()
            ConfigManager().github_pat = self._pending_pat
        super().closeEvent(event)

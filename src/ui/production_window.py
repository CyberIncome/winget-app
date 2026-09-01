"""Final production window compatibility and safety layer."""

from __future__ import annotations

import time

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import QHeaderView, QTableView

from src.logic.executor import is_valid_app_id
from src.ui.hardened_window import HardenedMainWindow
from src.ui.main_window import UpdateModel


class ProductionUpdateModel(UpdateModel):
    """Update model that preserves the source field required by the product spec."""

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

    def data(self, index, role=Qt.DisplayRole):
        if (
            index.isValid()
            and not self._is_inventory
            and role == Qt.DisplayRole
            and index.column() == 5
        ):
            return self._data[index.row()].get("Source", "")
        return super().data(index, role)


class ProductionMainWindow(HardenedMainWindow):
    """Apply final Qt and package-target safety guards."""

    def __init__(self):
        self._failed_start_pending = False
        super().__init__()
        self.process.started.connect(self._handle_process_started)

    # ── QProcess generation safety ──────────────────

    def handle_process_error(self, error):
        failed_to_start = (
            error == QProcess.FailedToStart
            or str(error).endswith("FailedToStart")
        )
        if failed_to_start:
            self._failed_start_pending = True
        super().handle_process_error(error)

    def _handle_process_started(self):
        self._failed_start_pending = False
        self._process_start_failed = False

    def process_finished(self, code, status):
        if self._failed_start_pending:
            self.logger.warning(
                "Ignoring finished signal for a failed-to-start generation."
            )
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

    def _detective_job_succeeded(self, results):
        """Keep detective-only update hits informational, not executable."""
        model = self.proxy_model.sourceModel()
        existing_objects = (
            {id(item) for item in model._data} if model is not None else set()
        )
        super()._detective_job_succeeded(results)
        model = self.proxy_model.sourceModel()
        if model is None:
            return
        for item in model._data:
            if id(item) not in existing_objects:
                item["UpdateSource"] = "detective"

    @staticmethod
    def _package_ref_for_winget_item(item):
        package_id = item.get("Id")
        if is_valid_app_id(package_id):
            return {"value": package_id, "match_by": "id"}
        name = str(item.get("Name") or "").strip()
        if name:
            return {"value": name, "match_by": "name"}
        return None

    @staticmethod
    def _is_winget_update_item(item):
        return item.get("UpdateSource", "winget") == "winget"

    def _selected_source_items(self, table, proxy):
        model = proxy.sourceModel() if proxy else None
        if model is None:
            return []

        checked = [
            item
            for item in model._data
            if model._selected.get(
                item.get("Id") or item.get("Name"), False
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
        """Map registry inventory rows back to proven Winget upgrade rows."""
        update_model = self.proxy_model.sourceModel()
        if update_model is None:
            return []

        by_id = {}
        by_name = {}
        for update_item in update_model._data:
            if not self._is_winget_update_item(update_item):
                continue
            package_id = str(update_item.get("Id") or "").strip().lower()
            name = str(update_item.get("Name") or "").strip().lower()
            if package_id:
                by_id.setdefault(package_id, []).append(update_item)
            if name:
                by_name.setdefault(name, []).append(update_item)

        refs = []
        seen = set()
        for inventory_item in inventory_items:
            package_id = str(
                inventory_item.get("Id") or ""
            ).strip().lower()
            name = str(
                inventory_item.get("Name") or ""
            ).strip().lower()

            candidates = by_id.get(package_id, []) if package_id else []
            if len(candidates) != 1:
                candidates = by_name.get(name, []) if name else []
            if len(candidates) != 1:
                continue

            ref = self._package_ref_for_winget_item(candidates[0])
            if ref is None:
                continue
            key = (ref["match_by"], ref["value"].lower())
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
                key = (ref["match_by"], ref["value"].lower())
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
            key = (ref["match_by"], ref["value"].lower())
            if key not in seen:
                refs.append(ref)
                seen.add(key)
        if refs:
            self.logger.info(
                "User requested update all for %d Winget-proven app(s).",
                len(refs),
            )
            self.batch_update(refs)

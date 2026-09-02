"""Interactive workbench features layered above the product/history window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.logic.worker_jobs import package_show_worker, winget_export_worker
from src.ui.product_window import ProductMainWindow


class WorkbenchMainWindow(ProductMainWindow):
    """Add user-controlled backup, inspection, and update cancellation tools."""

    def __init__(self):
        super().__init__()
        self._install_workbench_tools()

    def _install_workbench_tools(self):
        group = QWidget()
        group.setObjectName("apiStatusGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel("Backup & Package Tools")
        title.setObjectName("settingsLabel")
        layout.addWidget(title)
        hint = QLabel(
            "Create a native WinGet restore list for another Windows setup. "
            "This only reads installed package registrations and writes JSON; "
            "it does not install or remove software."
        )
        hint.setWordWrap(True)
        hint.setObjectName("apiStatusHint")
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.export_versions_cb = QCheckBox("Include currently installed versions")
        self.export_versions_cb.setToolTip(
            "Leave off for a restore list that installs current available versions; "
            "enable to ask WinGet to record installed versions where supported."
        )
        self.export_winget_btn = QPushButton("Export WinGet Restore List")
        self.export_winget_btn.clicked.connect(self.export_winget_restore_list)
        row.addWidget(self.export_versions_cb)
        row.addStretch()
        row.addWidget(self.export_winget_btn)
        layout.addLayout(row)

        settings_layout = self.settings_tab.layout()
        settings_layout.insertWidget(max(0, settings_layout.count() - 1), group)

        self.cancel_batch_btn = QPushButton("Cancel Update Batch")
        self.cancel_batch_btn.setVisible(False)
        self.cancel_batch_btn.clicked.connect(self.cancel_update_batch)
        self.statusBar().addPermanentWidget(self.cancel_batch_btn)

        # Replace the lower experience context menu with the richer canonical
        # workbench menu. Disconnect only this signal on the dedicated table.
        try:
            self.table.customContextMenuRequested.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            self._show_workbench_update_context_menu
        )

    # ── Native WinGet backup ────────────────────────

    def export_winget_restore_list(self):
        if self._is_closing or "winget-export" in self._managed_jobs:
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export WinGet Restore List",
            "winget-packages.json",
            "JSON files (*.json)",
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != ".json":
            destination = destination.with_suffix(".json")
        try:
            destination = destination.expanduser().resolve()
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Export WinGet Restore List",
                f"The selected destination could not be resolved: {exc}",
            )
            return
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Export WinGet Restore List",
                f"The destination directory could not be created: {exc}",
            )
            return

        include_versions = self.export_versions_cb.isChecked()
        self.export_winget_btn.setEnabled(False)
        started = self._start_job(
            "winget-export",
            winget_export_worker,
            args=(str(destination), include_versions),
            timeout=240,
            on_success=self._winget_export_succeeded,
            on_failure=self._winget_export_failed,
        )
        if not started:
            self.export_winget_btn.setEnabled(True)

    def _winget_export_succeeded(self, payload):
        if self._is_closing:
            return
        self.export_winget_btn.setEnabled(True)
        payload = payload or {}
        path = Path(str(payload.get("path") or ""))
        self.status_label.setText(f"WinGet restore list exported: {path.name}")
        self._record_event_safely(
            "winget-export",
            {
                "filename": path.name,
                "bytes": payload.get("size"),
                "include_versions": bool(payload.get("include_versions")),
            },
        )
        QMessageBox.information(
            self,
            "WinGet Restore List",
            (
                f"Exported {path.name}.\n\n"
                "Restore later with WinGet's import command after reviewing "
                "the JSON package list."
            ),
        )

    def _winget_export_failed(self, message):
        if self._is_closing:
            return
        self.export_winget_btn.setEnabled(True)
        self.logger.warning("WinGet restore-list export failed: %s", message)
        QMessageBox.warning(
            self,
            "WinGet Restore List",
            f"WinGet could not create a valid restore list:\n\n{message}",
        )

    # ── Rich package inspection ─────────────────────

    def _show_workbench_update_context_menu(self, position):
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        model = self.proxy_model.sourceModel()
        if model is None:
            return
        source_index = self.proxy_model.mapToSource(index)
        row = source_index.row()
        if not 0 <= row < len(model._data):
            return
        item = model._data[row]

        menu = QMenu(self)
        if self._is_winget_update_item(item):
            ref = self._package_ref_for_winget_item(item)
            if ref is not None:
                update_action = menu.addAction("Update Now")
                update_action.triggered.connect(
                    lambda _checked=False, package_ref=ref: self.batch_update(
                        [package_ref]
                    )
                )
                details_action = menu.addAction("View WinGet Package Details")
                details_action.triggered.connect(
                    lambda _checked=False, package_ref=ref: self.show_winget_details(
                        package_ref
                    )
                )
        skip_action = menu.addAction("Skip This Update Version")
        skip_action.triggered.connect(
            lambda _checked=False, row_item=dict(item): self.ignore_update(
                row_item
            )
        )
        identifier = item.get("Id") or item.get("Name")
        if identifier:
            copy_action = menu.addAction("Copy Package ID")
            copy_action.triggered.connect(
                lambda _checked=False, value=str(identifier): (
                    QApplication.clipboard().setText(value)
                    if QApplication.clipboard() is not None
                    else None
                )
            )
        menu.exec(self.table.viewport().mapToGlobal(position))

    def show_winget_details(self, package_ref):
        if self._is_closing or "package-show" in self._managed_jobs:
            return
        ref = dict(package_ref or {})
        self.status_label.setText(
            f"Loading WinGet details for {ref.get('value', 'package')}..."
        )
        self._start_job(
            "package-show",
            package_show_worker,
            args=(ref,),
            timeout=120,
            on_success=self._package_show_succeeded,
            on_failure=self._package_show_failed,
        )

    def _package_show_succeeded(self, payload):
        if self._is_closing:
            return
        payload = payload or {}
        ref = payload.get("ref") or {}
        output = str(payload.get("output") or "").strip()
        self.update_details.setPlainText(
            output or "WinGet returned no package metadata text."
        )
        self.status_label.setText(
            f"Loaded WinGet details for {ref.get('value', 'package')}"
        )
        self._record_event_safely(
            "package-details",
            {
                "package": ref.get("value"),
                "source": ref.get("source"),
            },
        )

    def _package_show_failed(self, message):
        if self._is_closing:
            return
        self.status_label.setText("WinGet package details could not be loaded")
        self.logger.warning("WinGet package detail lookup failed: %s", message)

    # ── Update-batch cancellation / start accounting ─

    def batch_update(self, package_refs):
        result = super().batch_update(package_refs)
        self.cancel_batch_btn.setVisible(
            self.current_operation == "update" or "update" in self._active_tasks
        )
        return result

    def run_next_update(self):
        tracker = self._batch_tracker
        result = super().run_next_update()
        if (
            tracker is not None
            and self.current_operation == "update"
            and getattr(self, "current_package_ref", None)
        ):
            try:
                state = self.process.state()
            except Exception:
                state = None
            if state == QProcess.NotRunning:
                tracker.record_failure(
                    dict(self.current_package_ref),
                    "failed before process start",
                )
        return result

    def cancel_update_batch(self):
        if self.current_operation != "update" and "update" not in self._active_tasks:
            self.cancel_batch_btn.setVisible(False)
            return

        tracker = self._batch_tracker
        refs = []
        current = getattr(self, "current_package_ref", None)
        if current:
            refs.append(dict(current))
        refs.extend(
            dict(ref)
            for ref in list(getattr(self, "process_queue", []) or [])
        )
        if tracker is not None:
            tracker.record_many_failures(refs, "cancelled by user")

        if hasattr(self, "process_queue"):
            self.process_queue.clear()
        self.current_operation = None
        self._process_crashed = False
        self._process_timed_out = False
        self._process_start_failed = False
        if hasattr(self, "_failed_start_pending"):
            self._failed_start_pending = False
        self.activity_progress.setText("")
        self._stop_timer_safely(self.process_timeout_timer, "process watchdog")
        self._stop_qprocess_safely()
        self.set_ui_busy("Update cancelled.", False, "update")
        self.cancel_batch_btn.setVisible(False)
        self._record_event_safely(
            "update-batch-cancel",
            {"cancelled_refs": len(refs)},
        )
        self._finish_batch_if_done()

    def _finish_batch_if_done(self):
        result = super()._finish_batch_if_done()
        if self._batch_tracker is None:
            self.cancel_batch_btn.setVisible(False)
        return result

"""User-facing product experience layered above the accepted runtime core."""

from __future__ import annotations

import json
import sys

from PySide6.QtCore import QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.app_info import (
    APP_RELEASES_URL,
    get_app_version,
    get_build_info,
    short_build_label,
)
from src.logic.config import ConfigManager
from src.logic.update_batch import BatchResultTracker
from src.logic.update_policy import filter_ignored_updates, package_identity
from src.logic.worker_jobs import app_release_worker, diagnostics_worker
from src.ui.runtime_window import RuntimeMainWindow


class ExperienceMainWindow(RuntimeMainWindow):
    """Add product UX without weakening the runtime reliability boundary."""

    def __init__(self):
        self._batch_tracker: BatchResultTracker | None = None
        self._latest_release: dict[str, object] | None = None
        self._ignored_filtered_count = 0
        super().__init__()
        self._install_product_experience()
        if (
            "pytest" not in sys.modules
            and ConfigManager().check_app_updates
        ):
            QTimer.singleShot(3000, self.check_app_release)

    # ── Settings / About / release awareness ───────

    def _install_product_experience(self):
        version = get_app_version()
        self.setWindowTitle(f"Winget Universal Dashboard {version}")

        settings_layout = self.settings_tab.layout()
        insert_index = max(0, settings_layout.count() - 1)

        group = QWidget()
        group.setObjectName("apiStatusGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel("Application")
        title.setObjectName("settingsLabel")
        layout.addWidget(title)

        self.app_version_lbl = QLabel(
            f"Version {version}  •  build {short_build_label()}"
        )
        self.app_version_lbl.setObjectName("apiStatusValue")
        layout.addWidget(self.app_version_lbl)

        self.app_release_status_lbl = QLabel("Release status: not checked")
        self.app_release_status_lbl.setObjectName("apiStatusHint")
        layout.addWidget(self.app_release_status_lbl)

        button_row = QHBoxLayout()
        self.app_release_check_btn = QPushButton("Check for App Update")
        self.app_release_check_btn.clicked.connect(self.check_app_release)
        self.app_release_open_btn = QPushButton("Open Releases")
        self.app_release_open_btn.clicked.connect(self.open_app_release)
        self.about_btn = QPushButton("About")
        self.about_btn.clicked.connect(self.show_about)
        self.copy_diagnostics_btn = QPushButton("Copy Diagnostics")
        self.copy_diagnostics_btn.clicked.connect(self.copy_diagnostics)
        for button in (
            self.app_release_check_btn,
            self.app_release_open_btn,
            self.about_btn,
            self.copy_diagnostics_btn,
        ):
            button_row.addWidget(button)
        layout.addLayout(button_row)

        config = ConfigManager()
        self.check_app_updates_cb = QCheckBox(
            "Automatically check for new dashboard releases"
        )
        self.check_app_updates_cb.setChecked(config.check_app_updates)
        self.check_app_updates_cb.toggled.connect(
            lambda value: setattr(
                ConfigManager(), "check_app_updates", bool(value)
            )
        )
        layout.addWidget(self.check_app_updates_cb)

        self.confirm_updates_cb = QCheckBox(
            "Confirm before starting package updates"
        )
        self.confirm_updates_cb.setChecked(config.confirm_updates)
        self.confirm_updates_cb.toggled.connect(
            lambda value: setattr(
                ConfigManager(), "confirm_updates", bool(value)
            )
        )
        layout.addWidget(self.confirm_updates_cb)

        self.auto_detective_cb = QCheckBox(
            "Run remote-version detective after inventory scans"
        )
        self.auto_detective_cb.setChecked(config.auto_detective)
        self.auto_detective_cb.toggled.connect(
            lambda value: setattr(
                ConfigManager(), "auto_detective", bool(value)
            )
        )
        layout.addWidget(self.auto_detective_cb)

        ignored_row = QHBoxLayout()
        self.ignored_updates_lbl = QLabel("")
        self.ignored_updates_lbl.setObjectName("apiStatusHint")
        self.restore_ignored_btn = QPushButton("Restore Ignored Updates")
        self.restore_ignored_btn.clicked.connect(self.restore_ignored_updates)
        ignored_row.addWidget(self.ignored_updates_lbl)
        ignored_row.addStretch()
        ignored_row.addWidget(self.restore_ignored_btn)
        layout.addLayout(ignored_row)
        self._refresh_ignored_settings()

        settings_layout.insertWidget(insert_index, group)

        self.release_notice_btn = QPushButton("")
        self.release_notice_btn.setVisible(False)
        self.release_notice_btn.clicked.connect(self.open_app_release)
        self.statusBar().addPermanentWidget(self.release_notice_btn)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            self._show_update_context_menu
        )

    def check_app_release(self):
        if self._is_closing or "app-release" in self._managed_jobs:
            return
        self.app_release_status_lbl.setText("Release status: checking...")
        self.app_release_check_btn.setEnabled(False)
        started = self._start_job(
            "app-release",
            app_release_worker,
            args=(get_app_version(), ConfigManager().github_pat),
            timeout=20,
            on_success=self._app_release_succeeded,
            on_failure=self._app_release_failed,
        )
        if not started:
            self.app_release_check_btn.setEnabled(True)

    def _app_release_succeeded(self, result):
        if self._is_closing:
            return
        self.app_release_check_btn.setEnabled(True)
        result = result or {}
        self._latest_release = result
        status = result.get("status")
        latest = result.get("latest_version")
        if status == "no-release":
            self.app_release_status_lbl.setText(
                "Release status: no published stable release yet"
            )
            self.release_notice_btn.setVisible(False)
            return
        if result.get("update_available"):
            self.app_release_status_lbl.setText(
                f"Release status: version {latest} is available"
            )
            self.app_release_open_btn.setText("Download Update")
            self.release_notice_btn.setText(f"Update available: {latest}")
            self.release_notice_btn.setVisible(True)
            return
        self.app_release_status_lbl.setText(
            f"Release status: up to date ({latest or get_app_version()})"
        )
        self.app_release_open_btn.setText("Open Releases")
        self.release_notice_btn.setVisible(False)

    def _app_release_failed(self, message):
        if self._is_closing:
            return
        self.app_release_check_btn.setEnabled(True)
        self.app_release_status_lbl.setText(
            "Release status: check failed; see console/log"
        )
        self.logger.warning("Application release check failed: %s", message)

    def open_app_release(self):
        result = self._latest_release or {}
        url = (
            result.get("installer_url")
            if result.get("update_available")
            else result.get("release_url")
        )
        QDesktopServices.openUrl(QUrl(str(url or APP_RELEASES_URL)))

    def show_about(self):
        info = get_build_info()
        commit = info.get("commit") or "development"
        dirty = " (dirty)" if info.get("dirty") is True else ""
        QMessageBox.information(
            self,
            "About Winget Universal Dashboard",
            (
                f"Winget Universal Dashboard {info['version']}\n"
                f"Build: {commit}{dirty}\n\n"
                "A source-aware Windows package update and system inventory "
                "dashboard powered by Winget."
            ),
        )

    def copy_diagnostics(self):
        if self._is_closing or "diagnostics" in self._managed_jobs:
            return
        self.copy_diagnostics_btn.setEnabled(False)
        started = self._start_job(
            "diagnostics",
            diagnostics_worker,
            timeout=15,
            on_success=self._diagnostics_succeeded,
            on_failure=self._diagnostics_failed,
        )
        if not started:
            self.copy_diagnostics_btn.setEnabled(True)

    def _diagnostics_succeeded(self, payload):
        if self._is_closing:
            return
        self.copy_diagnostics_btn.setEnabled(True)
        text = json.dumps(payload or {}, indent=2, sort_keys=True)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.status_label.setText("Diagnostics copied to clipboard")

    def _diagnostics_failed(self, message):
        if self._is_closing:
            return
        self.copy_diagnostics_btn.setEnabled(True)
        self.status_label.setText("Diagnostics collection failed")
        self.logger.warning("Diagnostics collection failed: %s", message)

    # ── Ignore/update policy ────────────────────────

    def _refresh_ignored_settings(self):
        count = len(ConfigManager().ignored_updates)
        self.ignored_updates_lbl.setText(
            f"Ignored package updates: {count}"
        )
        self.restore_ignored_btn.setEnabled(count > 0)

    def apply_winget_results(self, data):
        filtered, removed = filter_ignored_updates(
            list(data or []), ConfigManager().ignored_updates
        )
        self._ignored_filtered_count = removed
        if removed:
            self.logger.info(
                "Filtered %d ignored Winget update(s).", removed
            )
        super().apply_winget_results(filtered)
        self._refresh_ignored_settings()

    def _detective_job_succeeded(self, results):
        super()._detective_job_succeeded(results)
        self._purge_ignored_model_rows()

    def _purge_ignored_model_rows(self):
        model = self.proxy_model.sourceModel()
        if model is None:
            return
        kept, removed = filter_ignored_updates(
            list(model._data), ConfigManager().ignored_updates
        )
        if not removed:
            return
        model.beginResetModel()
        model._data = kept
        valid_keys = {
            model.selection_key_for_item(item) for item in kept
        }
        model._selected = {
            key: value
            for key, value in model._selected.items()
            if key in valid_keys
        }
        model.endResetModel()
        self._stat_updates = len(kept)
        self.update_stats()

    def _show_update_context_menu(self, position):
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
        ignore_action = menu.addAction("Ignore This Package Update")
        ignore_action.triggered.connect(
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

    def ignore_update(self, item):
        identity = package_identity(item)
        if not identity:
            return
        if ConfigManager().ignore_update(identity):
            self.logger.info("Ignored package update identity=%s", identity)
        self._purge_ignored_model_rows()
        self._refresh_ignored_settings()
        self.status_label.setText(
            "Package update ignored; restore it from Settings"
        )

    def restore_ignored_updates(self):
        ConfigManager().clear_ignored_updates()
        self._refresh_ignored_settings()
        self.status_label.setText(
            "Ignored updates restored; refresh updates to show them again"
        )

    # ── Safer update execution / result summary ─────

    def _confirm_batch(self, package_refs) -> bool:
        if not ConfigManager().confirm_updates:
            return True
        count = len(package_refs)
        if count == 1:
            detail = str(package_refs[0].get("value") or "the selected package")
            text = f"Update {detail} now?"
        else:
            text = f"Update {count} Winget-proven packages now?"
        return (
            QMessageBox.question(
                self,
                "Confirm Package Update",
                text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def batch_update(self, package_refs):
        package_refs = [dict(ref) for ref in package_refs or [] if ref]
        if not package_refs:
            return None
        if not self._confirm_batch(package_refs):
            self.logger.info("Package update batch cancelled by user.")
            return None
        self._batch_tracker = BatchResultTracker(package_refs)
        result = super().batch_update(package_refs)
        if (
            "update" not in self._active_tasks
            and self.current_operation != "update"
        ):
            self._batch_tracker = None
        return result

    def run_next_update(self):
        result = super().run_next_update()
        if self.current_operation is None:
            QTimer.singleShot(0, self._finish_batch_if_done)
        return result

    def handle_process_error(self, error):
        failed_to_start = (
            error == QProcess.FailedToStart
            or str(error).endswith("FailedToStart")
        )
        tracker = self._batch_tracker
        refs = []
        if (
            failed_to_start
            and self.current_operation == "update"
            and tracker is not None
        ):
            current = getattr(self, "current_package_ref", None)
            if current:
                refs.append(dict(current))
            refs.extend(
                dict(ref)
                for ref in list(getattr(self, "process_queue", []) or [])
            )
        result = super().handle_process_error(error)
        if failed_to_start and tracker is not None:
            tracker.record_many_failures(refs, "winget failed to start")
            QTimer.singleShot(0, self._finish_batch_if_done)
        return result

    def process_finished(self, code, status):
        operation = self.current_operation
        tracker = self._batch_tracker
        current = dict(getattr(self, "current_package_ref", {}) or {})
        crashed = status == QProcess.CrashExit or getattr(
            self, "_process_crashed", False
        )
        timed_out = getattr(self, "_process_timed_out", False)
        normal_success = (
            operation == "update"
            and code == 0
            and not crashed
            and not timed_out
        )
        retryable = (
            operation == "update"
            and not crashed
            and not timed_out
            and current.get("silent", True)
            and not current.get("retried_without_silent", False)
            and code != 0
        )

        result = super().process_finished(code, status)

        if operation == "update" and tracker is not None and current:
            if normal_success:
                tracker.record_success(current)
            elif not retryable:
                if timed_out:
                    reason = "timeout"
                elif crashed:
                    reason = "crash"
                else:
                    reason = f"exit code {code}"
                tracker.record_failure(current, reason)
        self._finish_batch_if_done()
        return result

    def _finish_batch_if_done(self):
        tracker = self._batch_tracker
        if tracker is None or self._is_closing:
            return
        if (
            self.current_operation == "update"
            or getattr(self, "process_queue", None)
        ):
            return

        summary = tracker.summary()
        self._batch_tracker = None
        succeeded = summary["succeeded"]
        failed = summary["failed"]
        pending = summary["pending"]
        requested = summary["requested"]

        text = (
            f"Package update batch finished: {succeeded}/{requested} succeeded."
        )
        if failed:
            text += f" {failed} failed."
        if pending:
            text += f" {pending} did not reach a terminal result."
        self.status_label.setText(text)
        self.append_log(f"\n[*] {text}")

        if failed or pending:
            details = []
            for failure in summary["failures"]:
                ref = failure["ref"]
                details.append(
                    f"{ref.get('value', 'unknown')}: {failure['reason']}"
                )
            for ref in summary["pending_refs"]:
                details.append(
                    f"{ref.get('value', 'unknown')}: incomplete"
                )
            QMessageBox.warning(
                self,
                "Package Update Summary",
                text + ("\n\n" + "\n".join(details) if details else ""),
            )
        else:
            QMessageBox.information(
                self,
                "Package Update Summary",
                text,
            )

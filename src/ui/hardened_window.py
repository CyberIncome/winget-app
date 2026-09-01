"""Reliability-hardened production window.

The legacy ``MainWindow`` still owns presentation and table behavior. This
subclass replaces crash-sensitive orchestration with explicitly owned spawned
process jobs, staged startup, deterministic shutdown, and stricter Winget
process-state handling.
"""

from __future__ import annotations

from collections import deque
import logging
import os
import time
import uuid

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Qt
from PySide6.QtWidgets import QHeaderView, QMainWindow, QTableView

from src.logic.config import ConfigManager
from src.logic.worker_jobs import (
    detective_worker,
    github_rate_limit_worker,
    inventory_scan_worker,
    winget_parse_worker,
)
from src.ui.main_window import MainWindow, UpdateModel
from src.ui.process_jobs import ManagedProcessJob


class HardenedMainWindow(MainWindow):
    """Main window with owned background work and bounded failure paths."""

    def __init__(self):
        self._managed_jobs: dict[str, ManagedProcessJob] = {}
        self._startup_stage = "boot"
        self._process_started_at: float | None = None
        self._process_hard_timeout_secs = 300
        self._process_idle_warning_secs = 180
        self._process_idle_warning_issued = False
        self._process_crashed = False
        self._session_id = os.getenv("WUD_SESSION_ID") or uuid.uuid4().hex[:12]
        super().__init__()
        self._configure_pat_debounce()
        self.logger.info(
            "SESSION WINDOW READY id=%s pid=%s", self._session_id, os.getpid()
        )

    def startup_sequence(self):
        if self._is_closing:
            return
        self._startup_stage = "refresh"
        self.logger.info(
            "STARTUP STAGE id=%s stage=refresh", self._session_id
        )
        QTimer.singleShot(0, self.refresh_updates)

    def _start_job(
        self,
        name,
        target,
        args=(),
        timeout=180,
        on_success=None,
        on_failure=None,
    ):
        if self._is_closing:
            return False
        if self._managed_jobs.get(name) is not None:
            self.logger.warning("JOB DUPLICATE BLOCKED name=%s", name)
            return False

        job = ManagedProcessJob(
            name=name,
            target=target,
            args=tuple(args),
            timeout_seconds=timeout,
            parent=self,
        )
        self._managed_jobs[name] = job
        if on_success is not None:
            job.succeeded.connect(lambda _name, value: on_success(value))
        job.failed.connect(
            lambda _name, message: self._handle_job_failure(
                name, message, on_failure
            )
        )
        job.finished.connect(self._handle_job_finished)
        return job.start()

    def _handle_job_failure(self, name, message, callback=None):
        if self._is_closing:
            return
        self.logger.error("Background job failed: %s", message)
        self.append_log(f"\n[!] {message}")
        if callback is not None:
            callback(message)

    def _handle_job_finished(self, name):
        job = self._managed_jobs.pop(name, None)
        if job is not None:
            job.deleteLater()
        if self._is_closing:
            return

        if name == "inventory" and "inventory" in self._active_tasks:
            self.set_ui_busy(
                "Scanning system inventory...", False, "inventory"
            )
        elif name == "detective":
            self.set_ui_busy(
                "Detective: Finished.", False, "detective"
            )
            self._advance_startup_to_api()
        elif name == "github-api" and self._startup_stage == "api":
            self._startup_stage = "ready"
            self.logger.info("STARTUP COMPLETE id=%s", self._session_id)

    def _advance_startup_after_refresh(self):
        if self._is_closing or self._startup_stage not in {
            "refresh",
            "parse",
        }:
            return
        self._startup_stage = "inventory"
        self.logger.info(
            "STARTUP STAGE id=%s stage=inventory", self._session_id
        )
        QTimer.singleShot(250, self.refresh_inventory)

    def _advance_startup_to_api(self):
        if self._is_closing or self._startup_stage not in {
            "inventory",
            "detective",
        }:
            return
        self._startup_stage = "api"
        self.logger.info("STARTUP STAGE id=%s stage=api", self._session_id)
        QTimer.singleShot(100, self.update_github_api_status)

    def refresh_inventory(self):
        if self._is_closing or "inventory" in self._managed_jobs:
            return
        self.logger.info("User requested fresh inventory scan.")
        self.set_ui_busy(
            "Scanning system inventory...", True, "inventory"
        )
        started = self._start_job(
            "inventory",
            inventory_scan_worker,
            timeout=300,
            on_success=self._inventory_job_succeeded,
            on_failure=self._inventory_job_failed,
        )
        if not started and "inventory" in self._active_tasks:
            self.set_ui_busy(
                "Scanning system inventory...", False, "inventory"
            )

    def _inventory_job_succeeded(self, payload):
        if self._is_closing:
            return
        payload = payload or {}
        self._cached_reg_data = payload.get("registry") or []
        self.set_inventory_model(payload.get("inventory") or [])

    def _inventory_job_failed(self, _message):
        if self._startup_stage == "inventory":
            self._advance_startup_to_api()

    def set_inventory_model(self, data):
        if self._is_closing:
            return
        model = UpdateModel(data, is_inventory=True)
        model.check_toggled.connect(
            lambda row, checked: self.handle_native_checkbox(
                self.inventory_table,
                self.inventory_proxy,
                row,
                checked,
            )
        )
        self.inventory_proxy.setSourceModel(model)
        self.inventory_table.setSelectionMode(QTableView.ExtendedSelection)
        self.inventory_table.setSelectionBehavior(QTableView.SelectRows)

        header = self.inventory_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.inventory_table.setColumnWidth(0, 40)
        for column in range(1, model.columnCount()):
            column_name = model.headerData(column, Qt.Horizontal)
            mode = (
                QHeaderView.Stretch
                if column_name == "Name"
                else QHeaderView.ResizeToContents
            )
            header.setSectionResizeMode(column, mode)

        self._stat_installed = len(data)
        self._last_scan_time = time.strftime("%H:%M:%S")
        self.set_ui_busy(
            "Scanning system inventory...", False, "inventory"
        )

        if ConfigManager().auto_detective and data:
            if self._startup_stage == "inventory":
                self._startup_stage = "detective"
            self.set_ui_busy(
                "Detective: Checking for updates...", True, "detective"
            )
            started = self._start_job(
                "detective",
                detective_worker,
                args=(data, dict(ConfigManager().url_fallbacks)),
                timeout=300,
                on_success=self._detective_job_succeeded,
            )
            if not started:
                self.set_ui_busy(
                    "Detective: Checking for updates...",
                    False,
                    "detective",
                )
                self._advance_startup_to_api()
        else:
            self._advance_startup_to_api()

    def _detective_job_succeeded(self, results):
        if self._is_closing:
            return
        results = results or []
        inventory_model = self.inventory_proxy.sourceModel()
        update_model = self.proxy_model.sourceModel()
        if update_model is None:
            update_model = UpdateModel([])
            update_model.check_toggled.connect(
                lambda row, checked: self.handle_native_checkbox(
                    self.table,
                    self.proxy_model,
                    row,
                    checked,
                )
            )
            self.proxy_model.setSourceModel(update_model)

        existing = {}
        for item in update_model._data:
            for key in (item.get("Id"), item.get("Name")):
                if key:
                    existing[str(key).lower()] = item

        inventory_changed = False
        updates_changed = False
        for index, version in results:
            if (
                inventory_model is None
                or not 0 <= index < len(inventory_model._data)
            ):
                continue
            item = inventory_model._data[index]
            item["Available"] = version
            inventory_changed = True

            match = None
            for key in (item.get("Id"), item.get("Name")):
                if key and str(key).lower() in existing:
                    match = existing[str(key).lower()]
                    break
            if match is not None:
                match["Available"] = version
                updates_changed = True
                continue

            new_item = {
                "Name": item.get("Name", ""),
                "Id": item.get("Id", ""),
                "Version": item.get("Version", ""),
                "Available": version,
            }
            update_model._data.append(new_item)
            selection_key = new_item.get("Id") or new_item.get("Name")
            update_model._selected[selection_key] = False
            for key in (new_item.get("Id"), new_item.get("Name")):
                if key:
                    existing[str(key).lower()] = new_item
            updates_changed = True

        if inventory_changed and inventory_model is not None:
            inventory_model.layoutChanged.emit()
        if updates_changed:
            update_model.layoutChanged.emit()
            self._stat_updates = len(update_model._data)
            self.update_stats()

    def refresh_updates(self):
        if self._is_closing:
            return
        super().refresh_updates()

    def run_next_update(self):
        if self._is_closing:
            return
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
                command = self.executor.get_update_cmd(
                    ref_value, match_by, silent=silent
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

    def start_process_watchdog(self, timeout=300, idle_warning=180):
        self._process_started_at = time.monotonic()
        self._process_last_output = self._process_started_at
        self._process_hard_timeout_secs = timeout
        self._process_idle_warning_secs = idle_warning
        self._process_idle_warning_issued = False
        self._process_timed_out = False
        self._process_crashed = False
        self.process_timeout_timer.start()

    def check_process_timeout(self):
        if self.process.state() == QProcess.NotRunning:
            return
        now = time.monotonic()
        started = self._process_started_at or now
        last_output = self._process_last_output or started
        elapsed = now - started
        idle = now - last_output

        if (
            self._process_idle_warning_secs
            and idle >= self._process_idle_warning_secs
            and not self._process_idle_warning_issued
        ):
            self._process_idle_warning_issued = True
            self.logger.warning(
                "Process has produced no output for %.0fs; allowing it "
                "to continue. operation=%s",
                idle,
                self.current_operation,
            )

        if elapsed < self._process_hard_timeout_secs:
            return

        current = getattr(self, "current_package_ref", {})
        self._process_timed_out = True
        self.logger.error(
            "PROCESS HARD TIMEOUT operation=%s package=%s elapsed=%.0fs",
            self.current_operation,
            current.get("value", ""),
            elapsed,
        )
        self.process.kill()

    def handle_process_error(self, error):
        failed_to_start = (
            error == QProcess.FailedToStart
            or str(error).endswith("FailedToStart")
        )
        crashed = error == QProcess.Crashed or str(error).endswith(
            "Crashed"
        )

        if crashed:
            if self._process_timed_out:
                self.logger.warning(
                    "QProcess crash signal followed an intentional "
                    "watchdog kill."
                )
            else:
                self._process_crashed = True
                self.logger.error(
                    "QProcess child crashed. operation=%s package=%s",
                    self.current_operation,
                    getattr(self, "current_package_ref", {}).get(
                        "value", ""
                    ),
                )
            return

        if not failed_to_start:
            self.logger.error("Process error occurred: %s", error)
            return

        operation = self.current_operation
        self._process_start_failed = True
        message = (
            "winget could not be started. Confirm App Installer is "
            "installed and the winget app execution alias is enabled."
        )
        self.logger.error("%s Process error: %s", message, error)
        self.append_log(f"\n[!] {message}")
        self.process_timeout_timer.stop()

        if operation == "refresh":
            self.set_ui_busy(
                "Scanning for updates...", False, "refresh"
            )
            self.current_operation = None
            self._advance_startup_after_refresh()
        elif operation == "update":
            if getattr(self, "process_queue", None):
                QTimer.singleShot(100, self.run_next_update)
            else:
                self.current_operation = None
                self.set_ui_busy("Update failed.", False, "update")

    def process_finished(self, code, status):
        self.process_timeout_timer.stop()
        if self._process_start_failed:
            self._process_start_failed = False
            return
        if self._is_closing:
            return

        self._flush_terminal_line()
        operation = self.current_operation
        crashed = status == QProcess.CrashExit or self._process_crashed
        timed_out = self._process_timed_out
        self.logger.info(
            "PROCESS FINISH operation=%s code=%s status=%s "
            "crashed=%s timed_out=%s",
            operation,
            code,
            status,
            crashed,
            timed_out,
        )
        self.progress_bar.setValue(0)

        if operation == "refresh":
            if code != 0 or crashed or timed_out:
                if timed_out:
                    reason = "timed out"
                elif crashed:
                    reason = "crashed"
                else:
                    reason = f"exit {code}"
                self.logger.error("Winget refresh failed: %s", reason)
                self.append_log(
                    f"\n[!] Winget refresh failed: {reason}"
                )
                self.current_operation = None
                self.set_ui_busy(
                    "Scanning for updates...", False, "refresh"
                )
                self._advance_startup_after_refresh()
                return

            if self._startup_stage == "refresh":
                self._startup_stage = "parse"
            started = self._start_job(
                "winget-parse",
                winget_parse_worker,
                args=(self.full_output,),
                timeout=120,
                on_success=self._winget_parse_succeeded,
                on_failure=self._winget_parse_failed,
            )
            if not started:
                self._winget_parse_failed(
                    "Winget parse job did not start"
                )
            return

        if operation != "update":
            return

        normal_success = code == 0 and not crashed and not timed_out
        if normal_success and hasattr(self, "current_package_ref"):
            self.remove_package_from_model(self.current_package_ref)
        else:
            current = getattr(self, "current_package_ref", {})
            name = current.get("value", "unknown")
            retryable = (
                not crashed
                and not timed_out
                and current.get("silent", True)
                and not current.get("retried_without_silent", False)
            )
            if retryable:
                retry_ref = dict(current)
                retry_ref["silent"] = False
                retry_ref["retried_without_silent"] = True
                if not hasattr(self, "process_queue"):
                    self.process_queue = deque()
                self.process_queue.appendleft(retry_ref)
                message = (
                    f"Retrying {name} without --silent after normal "
                    "failure."
                )
            else:
                if timed_out:
                    reason = "timeout"
                elif crashed:
                    reason = "crash"
                else:
                    reason = f"exit code {code}"
                message = f"Update failed for {name} ({reason})."
            self.logger.warning(message)
            self.append_log(f"\n[!] {message}")

        self._process_crashed = False
        self._process_timed_out = False
        if getattr(self, "process_queue", None):
            QTimer.singleShot(500, self.run_next_update)
        else:
            self.current_operation = None
            self.activity_progress.setText("")
            self.set_ui_busy("Update complete.", False, "update")

    def _winget_parse_succeeded(self, data):
        if self._is_closing:
            return
        self.apply_winget_results(data or [])
        self.current_operation = None
        self._advance_startup_after_refresh()

    def _winget_parse_failed(self, message):
        if self._is_closing:
            return
        self.logger.error("Winget parse failed: %s", message)
        self.append_log(
            "\n[!] Winget output could not be parsed safely. Raw output "
            "remains available in the console/log."
        )
        self.current_operation = None
        self.set_ui_busy(
            "Scanning for updates...", False, "refresh"
        )
        self._advance_startup_after_refresh()

    def _configure_pat_debounce(self):
        self._pending_pat = self.pat_input.text()
        self._pat_save_timer = QTimer(self)
        self._pat_save_timer.setSingleShot(True)
        self._pat_save_timer.setInterval(800)
        self._pat_save_timer.timeout.connect(self._save_pending_pat)
        try:
            self.pat_input.textChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.pat_input.textChanged.connect(self._on_pat_text_changed)

    def _on_pat_text_changed(self, text):
        self._pending_pat = text
        self._pat_save_timer.start()

    def _save_pending_pat(self):
        if self._is_closing:
            return
        ConfigManager().github_pat = self._pending_pat
        self.update_github_api_status()

    def update_github_api_status(self):
        if self._is_closing or "github-api" in self._managed_jobs:
            return
        pat = ConfigManager().github_pat
        self._start_job(
            "github-api",
            github_rate_limit_worker,
            args=(pat,),
            timeout=15,
            on_success=self._github_api_succeeded,
        )

    def _github_api_succeeded(self, result):
        if self._is_closing:
            return
        result = result or {}
        status_code = result.get("status_code")
        if status_code == 200 and result.get("payload"):
            self.display_rate_limit(result["payload"])
        elif status_code == 401:
            self.log_signal.emit(
                "GitHub API: Unauthorized (Check your PAT)"
            )
        else:
            self.log_signal.emit(f"GitHub API: Error {status_code}")

    def closeEvent(self, event):
        if self._is_closing:
            QMainWindow.closeEvent(self, event)
            return
        self._is_closing = True
        self.logger.info(
            "SESSION CLOSE REQUEST id=%s jobs=%s operation=%s",
            self._session_id,
            sorted(self._managed_jobs),
            self.current_operation,
        )

        if (
            hasattr(self, "_pat_save_timer")
            and self._pat_save_timer.isActive()
        ):
            self._pat_save_timer.stop()
        if self._pat_status_timer and self._pat_status_timer.isActive():
            self._pat_status_timer.stop()
        if self.process_timeout_timer.isActive():
            self.process_timeout_timer.stop()

        for name, job in list(self._managed_jobs.items()):
            job.cancel("window closing")
            self.logger.info(
                "SESSION JOB STOPPED id=%s job=%s",
                self._session_id,
                name,
            )
        self._managed_jobs.clear()

        if self.process and self.process.state() != QProcess.NotRunning:
            self.logger.info(
                "SESSION QPROCESS STOP id=%s operation=%s",
                self._session_id,
                self.current_operation,
            )
            self.process.terminate()
            if not self.process.waitForFinished(750):
                self.process.kill()
                self.process.waitForFinished(1000)

        try:
            logging.getLogger().removeHandler(self._log_handler)
        except (AttributeError, RuntimeError):
            pass
        self.logger.info("SESSION CLEAN EXIT id=%s", self._session_id)
        QMainWindow.closeEvent(self, event)

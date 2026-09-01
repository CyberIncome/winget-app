"""Canonical runtime window with exception-contained process boundaries."""

from __future__ import annotations

import logging

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QMainWindow

from src.logic.config import ConfigManager
from src.ui.production_window import ProductionMainWindow


class RuntimeMainWindow(ProductionMainWindow):
    """Own final QProcess boundaries and application teardown."""

    def _stop_timer_safely(self, timer, label: str) -> None:
        if timer is None:
            return
        try:
            if timer.isActive():
                timer.stop()
        except Exception as exc:
            self.logger.debug("Could not stop %s timer: %s", label, exc)

    def _stop_qprocess_safely(self) -> None:
        """Boundedly stop QProcess while containing wrapper/handle failures."""
        process = getattr(self, "process", None)
        if process is None:
            return

        state = None
        try:
            state = process.state()
        except Exception as exc:
            self.logger.warning("QProcess state unavailable during stop: %s", exc)

        if state == QProcess.NotRunning:
            return

        try:
            process.terminate()
        except Exception as exc:
            self.logger.warning("QProcess terminate failed during stop: %s", exc)

        finished = False
        try:
            finished = bool(process.waitForFinished(750))
        except Exception as exc:
            self.logger.warning("QProcess wait failed during stop: %s", exc)

        if finished:
            return

        try:
            process.kill()
        except Exception as exc:
            self.logger.error("QProcess kill failed during stop: %s", exc)

        try:
            process.waitForFinished(1000)
        except Exception as exc:
            self.logger.warning("QProcess final wait failed during stop: %s", exc)

    def _recover_synchronous_process_failure(
        self, operation: str, boundary: str, exc: Exception
    ) -> None:
        """Contain a synchronous process API failure and restore a safe state."""
        self.logger.exception(
            "QProcess %s failed operation=%s: %s",
            boundary,
            operation,
            exc,
        )
        self._stop_qprocess_safely()
        self._recover_process_callback_failure(operation, boundary, exc)

    def refresh_updates(self):
        try:
            return super().refresh_updates()
        except Exception as exc:
            self._recover_synchronous_process_failure(
                "refresh", "refresh-start", exc
            )
            return None

    def batch_update(self, package_refs):
        try:
            return super().batch_update(package_refs)
        except Exception as exc:
            self._recover_synchronous_process_failure(
                "update", "batch-start", exc
            )
            return None

    def check_process_timeout(self):
        try:
            return super().check_process_timeout()
        except Exception as exc:
            operation = self.current_operation or "process"
            self._recover_synchronous_process_failure(
                operation, "watchdog", exc
            )
            return None

    def _flush_pending_pat_safely(self) -> None:
        timer = getattr(self, "_pat_save_timer", None)
        if timer is None:
            return
        try:
            active = timer.isActive()
        except Exception:
            active = False
        if not active:
            return
        try:
            timer.stop()
            ConfigManager().github_pat = getattr(self, "_pending_pat", "")
        except Exception as exc:
            self.logger.exception("Could not flush pending PAT during close: %s", exc)

    def closeEvent(self, event):
        """Close deterministically without allowing teardown errors to escape."""
        if self._is_closing:
            try:
                QMainWindow.closeEvent(self, event)
            except Exception:
                try:
                    event.accept()
                except Exception:
                    pass
            return

        self._flush_pending_pat_safely()
        self._is_closing = True
        self.logger.info(
            "SESSION CLOSE REQUEST id=%s jobs=%s operation=%s",
            self._session_id,
            sorted(self._managed_jobs),
            self.current_operation,
        )

        self._stop_timer_safely(
            getattr(self, "_pat_save_timer", None), "PAT save"
        )
        self._stop_timer_safely(
            getattr(self, "_pat_status_timer", None), "PAT status"
        )
        self._stop_timer_safely(
            getattr(self, "process_timeout_timer", None), "process watchdog"
        )

        for name, job in list(self._managed_jobs.items()):
            try:
                job.cancel("window closing")
            except Exception as exc:
                self.logger.exception(
                    "Managed job cancellation failed during close job=%s: %s",
                    name,
                    exc,
                )
                try:
                    job._cleanup_process(terminate=True)
                except Exception as cleanup_exc:
                    self.logger.exception(
                        "Managed job emergency cleanup failed job=%s: %s",
                        name,
                        cleanup_exc,
                    )
            self.logger.info(
                "SESSION JOB STOPPED id=%s job=%s",
                self._session_id,
                name,
            )
        self._managed_jobs.clear()

        self._stop_qprocess_safely()

        try:
            logging.getLogger().removeHandler(self._log_handler)
        except Exception:
            pass
        self.logger.info("SESSION CLEAN EXIT id=%s", self._session_id)

        try:
            QMainWindow.closeEvent(self, event)
        except Exception as exc:
            self.logger.warning("Qt base closeEvent failed: %s", exc)
            try:
                event.accept()
            except Exception:
                pass

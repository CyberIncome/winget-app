"""Canonical runtime window with exception-contained application shutdown."""

from __future__ import annotations

import logging

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QMainWindow

from src.logic.config import ConfigManager
from src.ui.production_window import ProductionMainWindow


class RuntimeMainWindow(ProductionMainWindow):
    """Own final teardown so Windows handle races cannot escape closeEvent."""

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
            self.logger.warning("QProcess state unavailable during close: %s", exc)

        if state == QProcess.NotRunning:
            return

        try:
            process.terminate()
        except Exception as exc:
            self.logger.warning("QProcess terminate failed during close: %s", exc)

        finished = False
        try:
            finished = bool(process.waitForFinished(750))
        except Exception as exc:
            self.logger.warning("QProcess wait failed during close: %s", exc)

        if finished:
            return

        try:
            process.kill()
        except Exception as exc:
            self.logger.error("QProcess kill failed during close: %s", exc)

        try:
            process.waitForFinished(1000)
        except Exception as exc:
            self.logger.warning("QProcess final wait failed during close: %s", exc)

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

"""Parallelized startup orchestration above the accepted product window stack."""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer

from src.logic.worker_jobs import inventory_scan_worker
from src.ui.version_integrity_window import VersionIntegrityMainWindow


class StartupOptimizedMainWindow(VersionIntegrityMainWindow):
    """Run independent base scans together and defer optional enrichment."""

    def __init__(self):
        self._startup_started_at: float | None = None
        self._startup_refresh_done = False
        self._startup_inventory_done = False
        self._deferred_startup_detective = None
        self._startup_background_detective = False
        self._startup_app_release_deferred = False
        super().__init__()

    def startup_sequence(self):
        """Start authoritative WinGet and local inventory scans concurrently."""
        if self._is_closing or self._startup_stage != "boot":
            return

        self._startup_stage = "parallel-base"
        self._startup_started_at = time.monotonic()
        self.logger.info(
            "STARTUP STAGE id=%s stage=parallel-base",
            self._session_id,
        )

        # The update scan owns the foreground QProcess. The independent local
        # inventory worker is intentionally *not* registered as a global busy
        # task during startup, so Updates becomes usable as soon as WinGet has
        # finished even if local inventory is still loading in the background.
        self.refresh_updates()
        QTimer.singleShot(0, self._start_startup_inventory_scan)

    def _start_startup_inventory_scan(self):
        if self._is_closing or self._startup_stage != "parallel-base":
            return
        if "inventory" in self._managed_jobs:
            return
        self.logger.info("Starting non-blocking startup inventory scan.")
        started = self._start_job(
            "inventory",
            inventory_scan_worker,
            timeout=180,
            on_success=self._inventory_job_succeeded,
            on_failure=self._inventory_job_failed,
        )
        if not started:
            self._inventory_job_failed("startup inventory worker did not start")

    def refresh_inventory(self):
        """Keep Detective results bound to the inventory snapshot they scanned."""
        if "detective" in self._managed_jobs:
            self.logger.info(
                "Inventory refresh blocked while Detective owns the current snapshot."
            )
            self.status_label.setText(
                "Inventory refresh will be available when background Detective finishes"
            )
            return
        return super().refresh_inventory()

    def set_ui_busy(self, status, busy, task_name="core"):
        """Do not make optional startup Detective enrichment block readiness."""
        if self._startup_stage == "parallel-base" and task_name == "detective":
            return
        return super().set_ui_busy(status, busy, task_name)

    def _start_job(
        self,
        name,
        target,
        args=(),
        timeout=180,
        on_success=None,
        on_failure=None,
    ):
        """Defer startup Detective until both authoritative base scans settle."""
        if (
            name == "detective"
            and self._startup_stage == "parallel-base"
            and not self._is_closing
        ):
            self._deferred_startup_detective = {
                "target": target,
                "args": tuple(args),
                "timeout": timeout,
                "on_success": on_success,
                "on_failure": on_failure,
            }
            self.logger.info(
                "STARTUP ENRICHMENT DEFERRED id=%s job=detective",
                self._session_id,
            )
            return True
        return super()._start_job(
            name,
            target,
            args=args,
            timeout=timeout,
            on_success=on_success,
            on_failure=on_failure,
        )

    def _advance_startup_after_refresh(self):
        if self._startup_stage == "parallel-base":
            if not self._startup_refresh_done:
                self._startup_refresh_done = True
                self._log_base_stage_complete("refresh")
            self._finish_startup_base_if_ready()
            return
        return super()._advance_startup_after_refresh()

    def _inventory_job_succeeded(self, payload):
        if self._startup_stage != "parallel-base":
            return super()._inventory_job_succeeded(payload)
        if self._is_closing:
            return

        payload = payload or {}
        self._cached_reg_data = payload.get("registry") or []
        self.set_inventory_model(payload.get("inventory") or [])
        timings = dict(payload.get("timings") or {})
        if timings:
            self.logger.info(
                "STARTUP INVENTORY PROFILE registry=%.3fs shortcuts=%.3fs "
                "assembly=%.3fs worker_total=%.3fs registry_items=%s inventory_items=%s",
                float(timings.get("registry_seconds") or 0.0),
                float(timings.get("shortcut_scan_seconds") or 0.0),
                float(timings.get("assembly_seconds") or 0.0),
                float(timings.get("worker_total_seconds") or 0.0),
                timings.get("registry_items", "?"),
                timings.get("inventory_items", "?"),
            )
        self._startup_inventory_done = True
        self._log_base_stage_complete("inventory")
        self._finish_startup_base_if_ready()

    def _inventory_job_failed(self, message):
        if self._startup_stage != "parallel-base":
            return super()._inventory_job_failed(message)
        self.logger.warning("Startup inventory unavailable: %s", message)
        self._startup_inventory_done = True
        self._log_base_stage_complete("inventory-failed")
        self._finish_startup_base_if_ready()

    def _advance_startup_to_api(self):
        # The old serial startup used Detective completion to unlock the GitHub
        # API check. In the optimized lane both are optional post-ready work.
        if self._startup_stage in {"parallel-base", "ready"}:
            return
        return super()._advance_startup_to_api()

    def check_app_release(self):
        """Keep the dashboard's own network update check off the base startup path."""
        if self._startup_stage == "parallel-base":
            self._startup_app_release_deferred = True
            self.logger.info(
                "STARTUP ENRICHMENT DEFERRED id=%s job=app-release",
                self._session_id,
            )
            return
        return super().check_app_release()

    def _log_base_stage_complete(self, stage: str) -> None:
        started = self._startup_started_at
        elapsed = time.monotonic() - started if started is not None else 0.0
        self.logger.info(
            "STARTUP BASE STAGE COMPLETE id=%s stage=%s elapsed=%.3fs",
            self._session_id,
            stage,
            elapsed,
        )

    def _finish_startup_base_if_ready(self) -> None:
        if self._is_closing or self._startup_stage != "parallel-base":
            return
        if not (self._startup_refresh_done and self._startup_inventory_done):
            return

        self._startup_stage = "ready"
        started = self._startup_started_at
        elapsed = time.monotonic() - started if started is not None else 0.0
        self.logger.info(
            "STARTUP BASE READY id=%s elapsed=%.3fs",
            self._session_id,
            elapsed,
        )
        QTimer.singleShot(0, self._start_post_ready_enrichment)

    def _start_post_ready_enrichment(self) -> None:
        if self._is_closing or self._startup_stage != "ready":
            return

        deferred = self._deferred_startup_detective
        self._deferred_startup_detective = None
        if deferred is not None:
            started = super()._start_job(
                "detective",
                deferred["target"],
                args=deferred["args"],
                timeout=deferred["timeout"],
                on_success=deferred["on_success"],
                on_failure=deferred["on_failure"],
            )
            self._startup_background_detective = bool(started)
            if started:
                self.logger.info(
                    "STARTUP BACKGROUND ENRICHMENT id=%s job=detective",
                    self._session_id,
                )

        # Rate-limit status is informational. Run it after Ready so keyring and
        # network latency cannot extend the user's startup wait.
        QTimer.singleShot(0, self.update_github_api_status)
        if self._startup_app_release_deferred:
            self._startup_app_release_deferred = False
            QTimer.singleShot(0, self.check_app_release)

    def _handle_job_finished(self, name):
        if name == "detective" and self._startup_background_detective:
            job = self._managed_jobs.pop(name, None)
            if job is not None:
                job.deleteLater()
            self._startup_background_detective = False
            if not self._is_closing:
                self.logger.info(
                    "STARTUP BACKGROUND ENRICHMENT COMPLETE id=%s job=detective",
                    self._session_id,
                )
            return
        return super()._handle_job_finished(name)

"""Final product layer: operational memory, automation, and exports."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.logic.config import CONFIG_DIR, ConfigManager
from src.logic.history import (
    clear_history,
    export_dashboard_snapshot,
    load_history,
    record_event,
)
from src.logic.update_policy import update_skip_identity
from src.ui.experience_window import ExperienceMainWindow


_AUTO_REFRESH_OPTIONS = (0, 15, 30, 60, 120)


class ProductMainWindow(ExperienceMainWindow):
    """Add product features above the accepted experience/runtime stack."""

    def __init__(self):
        super().__init__()
        self._install_history_page()
        self._install_automation_settings()

    # ── History / export surface ────────────────────

    def _install_history_page(self):
        self._history_page_index = self.stack.count()
        self.sidebar.addItem("History")

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title = QLabel("Activity History")
        title.setObjectName("headerLabel")
        layout.addWidget(title)

        hint = QLabel(
            "Recent semantic dashboard events are kept locally and bounded to "
            "500 entries. Package command output remains in the normal logs."
        )
        hint.setWordWrap(True)
        hint.setObjectName("apiStatusHint")
        layout.addWidget(hint)

        controls = QHBoxLayout()
        refresh_btn = QPushButton("Refresh History")
        refresh_btn.clicked.connect(self.refresh_history_view)
        export_btn = QPushButton("Export Dashboard Snapshot")
        export_btn.clicked.connect(self.export_snapshot)
        open_data_btn = QPushButton("Open Data Folder")
        open_data_btn.clicked.connect(self.open_data_folder)
        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self.clear_history_view)
        for button in (refresh_btn, export_btn, open_data_btn, clear_btn):
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)

        self.history_view = QPlainTextEdit()
        self.history_view.setObjectName("detailsPane")
        self.history_view.setReadOnly(True)
        self.history_view.setMaximumBlockCount(2000)
        layout.addWidget(self.history_view, 1)

        self.stack.addWidget(page)
        self.refresh_history_view()

    def _record_event_safely(self, event_type: str, data: dict | None = None):
        # Tests and packaged smoke construction must not mutate the developer's
        # or verifier's real roaming profile merely by constructing a window.
        if "pytest" in sys.modules:
            return None
        try:
            event = record_event(event_type, data)
        except Exception as exc:
            self.logger.warning(
                "Could not persist activity history event %s: %s",
                event_type,
                exc,
            )
            return None
        if self.stack.currentIndex() == getattr(self, "_history_page_index", -1):
            self.refresh_history_view()
        return event

    def refresh_history_view(self):
        try:
            events = load_history(100)
        except Exception as exc:
            self.history_view.setPlainText(
                f"Could not read activity history: {exc}"
            )
            return

        if not events:
            self.history_view.setPlainText("No activity history recorded yet.")
            return

        lines = []
        for event in reversed(events):
            timestamp = str(event.get("timestamp") or "unknown-time")
            event_type = str(event.get("type") or "event")
            data = json.dumps(
                event.get("data") or {},
                ensure_ascii=False,
                sort_keys=True,
            )
            if len(data) > 1200:
                data = data[:1197] + "..."
            lines.append(f"{timestamp}  {event_type}\n  {data}")
        self.history_view.setPlainText("\n\n".join(lines))

    def clear_history_view(self):
        answer = QMessageBox.question(
            self,
            "Clear Activity History",
            "Delete the dashboard's bounded local activity history? Logs and "
            "configuration will not be removed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            removed = clear_history()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Clear Activity History",
                f"Could not clear activity history: {exc}",
            )
            return
        self.refresh_history_view()
        self.status_label.setText(f"Cleared {removed} activity history event(s)")

    def open_data_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(CONFIG_DIR))))

    @staticmethod
    def _model_rows(proxy) -> list[dict]:
        model = proxy.sourceModel() if proxy is not None else None
        if model is None:
            return []
        return [dict(item) for item in getattr(model, "_data", [])]

    def export_snapshot(self):
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Dashboard Snapshot",
            "WingetUniversalDashboard-snapshot.json",
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            destination = export_dashboard_snapshot(
                Path(path),
                updates=self._model_rows(self.proxy_model),
                inventory=self._model_rows(self.inventory_proxy),
                metadata={
                    "ignored_updates_count": len(ConfigManager().ignored_updates),
                    "ignored_updates_filtered_last_scan": self._ignored_filtered_count,
                    "last_scan_time": self._last_scan_time,
                    "auto_refresh_minutes": self._auto_refresh_minutes(),
                },
            )
        except Exception as exc:
            self.logger.exception("Dashboard snapshot export failed: %s", exc)
            QMessageBox.warning(
                self,
                "Export Dashboard Snapshot",
                f"Could not export the dashboard snapshot: {exc}",
            )
            return
        self.status_label.setText(f"Snapshot exported: {destination.name}")
        self._record_event_safely(
            "snapshot-export",
            {"filename": destination.name},
        )

    # ── Periodic read-only update scanning ──────────

    def _auto_refresh_minutes(self) -> int:
        value = ConfigManager().get("auto_refresh_minutes", 0)
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            return 0
        return minutes if minutes in _AUTO_REFRESH_OPTIONS else 0

    def _install_automation_settings(self):
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._auto_refresh_tick)

        group = QWidget()
        group.setObjectName("apiStatusGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel("Automation")
        title.setObjectName("settingsLabel")
        layout.addWidget(title)
        hint = QLabel(
            "Periodically rerun the read-only Winget update scan when the "
            "dashboard is otherwise idle. Automatic scans never install updates."
        )
        hint.setWordWrap(True)
        hint.setObjectName("apiStatusHint")
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.addWidget(QLabel("Automatic update scan:"))
        self.auto_refresh_combo = QComboBox()
        labels = {
            0: "Off",
            15: "Every 15 minutes",
            30: "Every 30 minutes",
            60: "Every hour",
            120: "Every 2 hours",
        }
        for minutes in _AUTO_REFRESH_OPTIONS:
            self.auto_refresh_combo.addItem(labels[minutes], minutes)
        current = self._auto_refresh_minutes()
        index = self.auto_refresh_combo.findData(current)
        self.auto_refresh_combo.setCurrentIndex(max(index, 0))
        self.auto_refresh_combo.currentIndexChanged.connect(
            self._auto_refresh_changed
        )
        row.addWidget(self.auto_refresh_combo)
        row.addStretch()
        layout.addLayout(row)

        settings_layout = self.settings_tab.layout()
        settings_layout.insertWidget(max(0, settings_layout.count() - 1), group)
        self._configure_auto_refresh(current)

    def _configure_auto_refresh(self, minutes: int):
        self._auto_refresh_timer.stop()
        if minutes in _AUTO_REFRESH_OPTIONS and minutes > 0:
            self._auto_refresh_timer.start(minutes * 60 * 1000)

    def _auto_refresh_changed(self, index: int):
        value = self.auto_refresh_combo.itemData(index)
        minutes = int(value) if value in _AUTO_REFRESH_OPTIONS else 0
        ConfigManager().set("auto_refresh_minutes", minutes)
        self._configure_auto_refresh(minutes)
        self._record_event_safely(
            "auto-refresh-setting",
            {"minutes": minutes},
        )

    def _auto_refresh_tick(self):
        if self._is_closing:
            return
        if self._active_tasks or self.current_operation or self._managed_jobs:
            self.logger.info(
                "Automatic update scan deferred because another task is active."
            )
            return
        self.logger.info("Automatic update scan triggered.")
        self.refresh_updates()

    # ── Semantic history boundaries ─────────────────

    def apply_winget_results(self, data):
        raw_count = len(data or [])
        result = super().apply_winget_results(data)
        shown = len(self._model_rows(self.proxy_model))
        self._record_event_safely(
            "update-scan",
            {
                "reported": raw_count,
                "visible": shown,
                "ignored": self._ignored_filtered_count,
            },
        )
        return result

    def set_inventory_model(self, data):
        result = super().set_inventory_model(data)
        self._record_event_safely(
            "inventory-scan",
            {"applications": len(data or [])},
        )
        return result

    def _app_release_succeeded(self, result):
        response = super()._app_release_succeeded(result)
        payload = result or {}
        self._record_event_safely(
            "app-release-check",
            {
                "status": payload.get("status"),
                "current_version": payload.get("current_version"),
                "latest_version": payload.get("latest_version"),
                "update_available": bool(payload.get("update_available")),
            },
        )
        return response

    def ignore_update(self, item):
        """Skip only the currently offered version; newer versions reappear."""
        identity = update_skip_identity(item)
        if not identity:
            self.status_label.setText(
                "This row does not have a specific update version to skip"
            )
            return None
        if ConfigManager().ignore_update(identity):
            self.logger.info("Skipped package update identity=%s", identity)
        self._purge_ignored_model_rows()
        self._refresh_ignored_settings()
        self.status_label.setText(
            "This update version was skipped; a newer version will appear normally"
        )
        self._record_event_safely(
            "skip-update-version",
            {"identity": identity},
        )
        return None

    def restore_ignored_updates(self):
        count = len(ConfigManager().ignored_updates)
        result = super().restore_ignored_updates()
        if count:
            self._record_event_safely(
                "restore-ignored-updates",
                {"restored": count},
            )
        return result

    def _finish_batch_if_done(self):
        tracker = self._batch_tracker
        result = super()._finish_batch_if_done()
        if tracker is not None and self._batch_tracker is None:
            summary = tracker.summary()
            failures = []
            for failure in summary["failures"]:
                ref = failure.get("ref") or {}
                failures.append(
                    {
                        "package": ref.get("value"),
                        "source": ref.get("source"),
                        "reason": failure.get("reason"),
                    }
                )
            self._record_event_safely(
                "update-batch",
                {
                    "requested": summary["requested"],
                    "succeeded": summary["succeeded"],
                    "failed": summary["failed"],
                    "pending": summary["pending"],
                    "failures": failures,
                },
            )
        return result

    def closeEvent(self, event):
        self._stop_timer_safely(
            getattr(self, "_auto_refresh_timer", None),
            "automatic refresh",
        )
        return super().closeEvent(event)

"""Version provenance and exact-target UX layered above the product workbench."""

from __future__ import annotations

import sys

from PySide6.QtCore import QProcessEnvironment, QTimer, Qt
from PySide6.QtWidgets import QMessageBox, QPushButton

from src.logic.config import ConfigManager
from src.logic.executor import validate_package_version
from src.logic.version_provenance import (
    annotate_version_row,
    merge_export_versions,
)
from src.logic.version_workers import (
    exact_package_show_worker,
    winget_version_map_worker,
)
from src.ui.workbench_window import WorkbenchMainWindow


class VersionAwareMainWindow(WorkbenchMainWindow):
    """Make mixed WinGet/Windows version schemes explicit and scan-bound."""

    def __init__(self):
        self._version_scan_generation = 0
        self._version_reconcile_pending = False
        super().__init__()
        self._install_version_experience()

    def _install_version_experience(self):
        self.version_review_btn = QPushButton("")
        self.version_review_btn.setVisible(False)
        self.version_review_btn.clicked.connect(self.show_version_review)
        self.statusBar().addPermanentWidget(self.version_review_btn)

        self.table.clicked.connect(self._render_clicked_version_context)
        # Historical UI used double-click as a mutating update shortcut. Replace
        # it with read-only package inspection; updates remain explicit actions.
        try:
            self.table.doubleClicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.table.doubleClicked.connect(self._double_click_package_details)

    # ── Scan annotation / source-version reconciliation ──────────────

    def apply_winget_results(self, data):
        self._version_scan_generation += 1
        generation = self._version_scan_generation
        annotated = [annotate_version_row(dict(item)) for item in (data or [])]
        result = super().apply_winget_results(annotated)
        self._apply_version_headers()
        self._refresh_version_review_button()
        if "pytest" not in sys.modules:
            self._start_version_reconciliation(generation)
        return result

    def _apply_version_headers(self):
        model = self.proxy_model.sourceModel()
        if model is None or len(getattr(model, "headers", [])) < 5:
            return
        model.headers[3] = "Installed (Windows)"
        model.headers[4] = "Target (WinGet)"
        try:
            model.headerDataChanged.emit(Qt.Horizontal, 3, 4)
        except Exception:
            pass

    def _start_version_reconciliation(self, generation: int | None = None):
        if self._is_closing:
            return
        generation = generation or self._version_scan_generation
        if "version-map" in self._managed_jobs:
            self._version_reconcile_pending = True
            return
        self._version_reconcile_pending = False
        started = self._start_job(
            "version-map",
            winget_version_map_worker,
            timeout=210,
            on_success=lambda payload, scan=generation: self._version_map_succeeded(
                scan, payload
            ),
            on_failure=self._version_map_failed,
        )
        if started:
            self.logger.info(
                "Reconciling Windows DisplayVersion values with WinGet source versions."
            )

    def _version_map_succeeded(self, generation: int, payload):
        if self._is_closing:
            return
        if generation != self._version_scan_generation:
            self._start_version_reconciliation(self._version_scan_generation)
            return
        model = self.proxy_model.sourceModel()
        if model is None:
            return
        records = list((payload or {}).get("records") or [])
        model._data = merge_export_versions(list(model._data), records)
        model.layoutChanged.emit()
        self._apply_version_headers()
        self._refresh_version_review_button()
        self.logger.info(
            "Version provenance reconciliation loaded %d source package version(s).",
            len(records),
        )
        self._record_event_safely(
            "version-provenance",
            {
                "source_versions": len(records),
                "review_rows": self._version_review_count(),
            },
        )
        if self._version_reconcile_pending:
            self._start_version_reconciliation(self._version_scan_generation)

    def _version_map_failed(self, message):
        if self._is_closing:
            return
        self.logger.warning("Source-version reconciliation unavailable: %s", message)
        self._refresh_version_review_button()
        if self._version_reconcile_pending:
            self._start_version_reconciliation(self._version_scan_generation)

    def _version_review_rows(self) -> list[dict]:
        model = self.proxy_model.sourceModel()
        if model is None:
            return []
        return [
            item
            for item in model._data
            if self._is_winget_update_item(item)
            and bool(item.get("VersionNeedsReview"))
        ]

    def _version_review_count(self) -> int:
        return len(self._version_review_rows())

    def _refresh_version_review_button(self):
        count = self._version_review_count()
        self.version_review_btn.setVisible(count > 0)
        if count:
            self.version_review_btn.setText(f"Version mapping review: {count}")
            self.version_review_btn.setToolTip(
                "These are still WinGet-reported upgrades, but Windows DisplayVersion "
                "and WinGet PackageVersion do not compare cleanly. Click to review."
            )

    def show_version_review(self):
        rows = self._version_review_rows()
        if not rows:
            QMessageBox.information(
                self,
                "Version Mapping Review",
                "No current WinGet update rows require version-mapping review.",
            )
            return
        lines = []
        for item in rows[:20]:
            source_installed = item.get("SourceInstalledVersion")
            mapped = (
                f" | source-installed {source_installed}"
                if source_installed
                else ""
            )
            lines.append(
                f"• {item.get('Name') or item.get('Id')}\n"
                f"  Windows {item.get('Version') or 'unknown'}{mapped} | "
                f"target {item.get('Available') or 'unknown'}\n"
                f"  {item.get('VersionExplanation') or 'Version schemes differ.'}"
            )
        if len(rows) > 20:
            lines.append(f"\n…and {len(rows) - 20} more row(s).")
        QMessageBox.warning(
            self,
            "Version Mapping Review",
            (
                "WinGet still reports every row below as upgradeable. This warning "
                "means the Windows-installed version and WinGet package version are "
                "not safely interpretable as one numbering scheme.\n\n"
                + "\n\n".join(lines)
            ),
        )

    # ── Local detail-pane version explanation ────────────────────────

    def _source_item_for_index(self, proxy_index):
        if not proxy_index.isValid():
            return None
        model = self.proxy_model.sourceModel()
        if model is None:
            return None
        source_index = self.proxy_model.mapToSource(proxy_index)
        row = source_index.row()
        if not 0 <= row < len(model._data):
            return None
        return model._data[row]

    @staticmethod
    def _version_context_text(item: dict) -> str:
        lines = [
            str(item.get("Name") or item.get("Id") or "Package"),
            f"Package ID: {item.get('Id') or 'unavailable'}",
            f"Source: {item.get('Source') or 'unavailable'}",
            "",
            f"Installed (Windows / Apps & Features): {item.get('Version') or 'unknown'}",
        ]
        if item.get("SourceInstalledVersion"):
            lines.append(
                "Installed (WinGet source mapping): "
                f"{item.get('SourceInstalledVersion')}"
            )
        lines.extend(
            [
                f"Target (WinGet package): {item.get('Available') or 'unknown'}",
                f"Version assessment: {item.get('VersionStatus') or 'not assessed'}",
                "",
                str(item.get("VersionExplanation") or ""),
            ]
        )
        if item.get("UpdateSource") == "winget":
            lines.extend(
                [
                    "",
                    "If updated, the dashboard will target the exact WinGet package "
                    "version shown above rather than whatever becomes latest later.",
                    "Double-click this row to load WinGet metadata for that exact target.",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "This is an informational detective row and cannot trigger a WinGet update.",
                ]
            )
        return "\n".join(lines)

    def _render_clicked_version_context(self, index):
        item = self._source_item_for_index(index)
        if item is not None:
            self.update_details.setPlainText(self._version_context_text(item))

    def _double_click_package_details(self, index):
        item = self._source_item_for_index(index)
        if item is None:
            return
        if not self._is_winget_update_item(item):
            self.update_details.setPlainText(self._version_context_text(item))
            return
        ref = self._package_ref_for_winget_item(item)
        if ref is None:
            self.update_details.setPlainText(self._version_context_text(item))
            return
        self.show_winget_details(ref)

    def show_winget_details(self, package_ref):
        """Load metadata for the exact target version shown by the current scan."""
        if self._is_closing or "package-show" in self._managed_jobs:
            return
        ref = dict(package_ref or {})
        self.status_label.setText(
            f"Loading WinGet details for {ref.get('value', 'package')} "
            f"{ref.get('version', '')}..."
        )
        self._start_job(
            "package-show",
            exact_package_show_worker,
            args=(ref,),
            timeout=120,
            on_success=self._package_show_succeeded,
            on_failure=self._package_show_failed,
        )

    def _package_show_succeeded(self, payload):
        super()._package_show_succeeded(payload)
        if self._is_closing:
            return
        ref = dict((payload or {}).get("ref") or {})
        item = self._find_item_for_ref(ref)
        if item is None:
            return
        metadata_text = self.update_details.toPlainText()
        self.update_details.setPlainText(
            self._version_context_text(item)
            + "\n\n--- WinGet package metadata ---\n"
            + metadata_text
        )

    def _find_item_for_ref(self, ref: dict):
        model = self.proxy_model.sourceModel()
        if model is None:
            return None
        target_key = self._package_ref_key(ref)
        for item in model._data:
            if not self._is_winget_update_item(item):
                continue
            candidate = self._package_ref_for_winget_item(item)
            if candidate is not None and self._package_ref_key(candidate) == target_key:
                return item
        return None

    # ── Exact scan-bound package execution ───────────────────────────

    def _package_ref_for_winget_item(self, item):
        ref = super()._package_ref_for_winget_item(item)
        if ref is None:
            return None
        try:
            target_version = validate_package_version(item.get("Available"))
        except ValueError:
            return None
        if not target_version:
            return None
        ref["version"] = target_version
        return ref

    @staticmethod
    def _package_ref_key(ref):
        return (
            str(ref.get("match_by") or "").casefold(),
            str(ref.get("value") or "").casefold(),
            str(ref.get("source") or "").casefold(),
            str(ref.get("version") or "").casefold(),
        )

    def _refs_requiring_version_review(self, refs) -> int:
        keys = {self._package_ref_key(ref) for ref in refs or []}
        count = 0
        for item in self._version_review_rows():
            candidate = self._package_ref_for_winget_item(item)
            if candidate is not None and self._package_ref_key(candidate) in keys:
                count += 1
        return count

    def _confirm_batch(self, package_refs) -> bool:
        review_count = self._refs_requiring_version_review(package_refs)
        if not review_count or not ConfigManager().confirm_updates:
            return super()._confirm_batch(package_refs)
        count = len(package_refs)
        text = (
            f"Update {count} WinGet-proven package(s) now?\n\n"
            f"{review_count} selected package(s) use version values that do not "
            "compare cleanly between Windows and WinGet. WinGet still reports them "
            "as upgradeable. Review the Version Mapping warning if this is unexpected.\n\n"
            "The update commands will be pinned to the exact target versions shown "
            "in the current scan."
        )
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

    def run_next_update(self):
        """Run the next queued exact package/source/target-version update."""
        if self._is_closing:
            return
        if hasattr(self, "process_queue") and self.process_queue:
            tracker = self._batch_tracker
            self.current_package_ref = self.process_queue.popleft()
            ref_value = self.current_package_ref["value"]
            match_by = self.current_package_ref["match_by"]
            source = self.current_package_ref.get("source")
            target_version = self.current_package_ref.get("version")
            silent = self.current_package_ref.get("silent", True)
            self.logger.info(
                "Updating %s by %s source=%s target=%s (silent=%s)...",
                ref_value,
                match_by,
                source or "default",
                target_version or "latest",
                silent,
            )
            try:
                command = self.executor.get_update_cmd(
                    ref_value,
                    match_by,
                    silent=silent,
                    source=source,
                    version=target_version,
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
                self.logger.exception("Failed to start update for %s", ref_value)
                self.append_log(f"\n[!] Failed to start {ref_value}: {exc}")
                if tracker is not None:
                    tracker.record_failure(
                        dict(self.current_package_ref),
                        "failed before process start",
                    )
                QTimer.singleShot(100, self.run_next_update)
            return

        self.current_operation = None
        self.activity_progress.setText("")
        self.set_ui_busy("Update complete.", False, "update")
        QTimer.singleShot(0, self._finish_batch_if_done)

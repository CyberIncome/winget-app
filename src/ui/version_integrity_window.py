"""Final integrity and small quality-of-life guards for the canonical GUI."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from src.ui.version_aware_window import VersionAwareMainWindow


class VersionIntegrityMainWindow(VersionAwareMainWindow):
    """Close version lifecycle races and add low-risk interaction polish."""

    def __init__(self):
        super().__init__()
        self._install_update_qol()

    # ── Small interaction/QoL improvements ───────────────────────────

    def _install_update_qol(self):
        toolbar = QWidget()
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(8)

        self.update_filter_summary = QLabel("")
        self.update_filter_summary.setObjectName("apiStatusHint")
        layout.addWidget(self.update_filter_summary)
        layout.addStretch()

        select_visible_btn = QPushButton("Select Visible Rows")
        select_visible_btn.setToolTip(
            "Select/check rows currently visible through the search filter"
        )
        select_visible_btn.clicked.connect(self.table.selectAll)
        clear_selection_btn = QPushButton("Clear Selection")
        clear_selection_btn.clicked.connect(self.table.clearSelection)
        self.clear_search_btn = QPushButton("Clear Search")
        self.clear_search_btn.clicked.connect(self.search_bar.clear)
        for button in (
            select_visible_btn,
            clear_selection_btn,
            self.clear_search_btn,
        ):
            layout.addWidget(button)

        hint = QLabel("Double-click = read-only details • Update buttons = install")
        hint.setObjectName("apiStatusHint")
        hint.setToolTip(
            "Inspecting a row never installs software. Package changes only start "
            "from the explicit Update controls and confirmation flow."
        )
        layout.addWidget(hint)

        update_layout = self.update_tab.layout()
        if update_layout is not None:
            update_layout.insertWidget(0, toolbar)

        # Inventory historically inherited the same double-click-to-update
        # shortcut as Updates. Keep double-click read-only throughout the app.
        try:
            self.inventory_table.doubleClicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.inventory_table.doubleClicked.connect(
            lambda index: self.handle_table_click(self.inventory_table, index)
        )

        self.table.setToolTip(
            "Installed (Windows) is the Apps & Features/ARP display version. "
            "Target (WinGet) is the source package version WinGet reports. "
            "These numbering schemes can legitimately differ."
        )
        self.search_bar.textChanged.connect(
            lambda _text: QTimer.singleShot(0, self._refresh_update_filter_summary)
        )
        self._refresh_update_filter_summary()

    def _refresh_update_filter_summary(self):
        if not hasattr(self, "update_filter_summary"):
            return
        model = self.proxy_model.sourceModel()
        total = len(getattr(model, "_data", [])) if model is not None else 0
        visible = self.proxy_model.rowCount()
        review = self._version_review_count()
        text = f"{visible} shown / {total} total"
        if review:
            text += f" • {review} version mapping review"
        self.update_filter_summary.setText(text)
        self.clear_search_btn.setEnabled(bool(self.search_bar.text()))

    @staticmethod
    def _complete_scan_target(value) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        lowered = text.casefold()
        if lowered in {"unknown", "???"}:
            return False
        if "…" in text or text.endswith("..."):
            return False
        return True

    def apply_winget_results(self, data):
        result = super().apply_winget_results(data)
        model = self.proxy_model.sourceModel()
        if model is not None:
            changed = False
            for item in model._data:
                if not self._is_winget_update_item(item):
                    continue
                if self._complete_scan_target(item.get("Available")):
                    continue
                item["VersionStatus"] = "incomplete-target"
                item["VersionNeedsReview"] = True
                item["VersionExplanation"] = (
                    "WinGet's displayed target version is incomplete or unknown. "
                    "This row is informational until a fresh scan yields a complete "
                    "exact package version; no update command will be generated."
                )
                changed = True
            if changed:
                model.layoutChanged.emit()
                self._refresh_version_review_button()
        self._refresh_update_filter_summary()
        return result

    def _purge_ignored_model_rows(self):
        result = super()._purge_ignored_model_rows()
        self._refresh_update_filter_summary()
        return result

    def _detective_job_succeeded(self, results):
        result = super()._detective_job_succeeded(results)
        self._refresh_update_filter_summary()
        return result

    # ── Managed-job/version identity integrity ───────────────────────

    def _handle_job_finished(self, name):
        """Restart deferred version reconciliation only after ownership releases."""
        super()._handle_job_finished(name)
        if self._is_closing:
            return
        if name == "version-map" and self._version_reconcile_pending:
            self._version_reconcile_pending = False
            self._start_version_reconciliation(self._version_scan_generation)

    def _package_ref_for_winget_item(self, item):
        """Reject incomplete display targets instead of falling back to latest."""
        if not self._complete_scan_target(item.get("Available")):
            return None
        return super()._package_ref_for_winget_item(item)

    def _confirm_batch(self, package_refs) -> bool:
        """Always surface version-scheme warnings, independent of normal prompts."""
        review_count = self._refs_requiring_version_review(package_refs)
        if not review_count:
            return super()._confirm_batch(package_refs)
        count = len(package_refs)
        return (
            QMessageBox.warning(
                self,
                "Confirm Version-Mapping Update",
                (
                    f"{review_count} of {count} selected package(s) use Windows and "
                    "WinGet version values that do not compare cleanly. WinGet still "
                    "reports them as upgradeable.\n\n"
                    "The dashboard will target the exact WinGet package versions shown "
                    "in the current scan. Continue only if those package/source targets "
                    "are expected."
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def remove_package_from_model(self, package_ref):
        """Remove a success row only when package/source/target all still match."""
        model = self.proxy_model.sourceModel()
        if model is None:
            return

        target = str(package_ref.get("value") or "").strip().casefold()
        match_by = str(package_ref.get("match_by") or "").strip().casefold()
        target_source = str(package_ref.get("source") or "").strip().casefold()
        target_version = str(package_ref.get("version") or "").strip().casefold()
        if match_by not in {"id", "name"} or not target:
            return

        for row_index, item in enumerate(model._data):
            current = item.get("Id") if match_by == "id" else item.get("Name")
            current = str(current or "").strip().casefold()
            item_source = str(item.get("Source") or "").strip().casefold()
            item_target = str(item.get("Available") or "").strip().casefold()
            if current != target:
                continue
            if target_source and item_source != target_source:
                continue
            if target_version and item_target != target_version:
                self.logger.warning(
                    "Update succeeded for scan target %s %s, but visible row now "
                    "offers %s; preserving the newer/different row.",
                    target,
                    target_version,
                    item_target or "unknown",
                )
                return

            selection_key = self._selection_key(model, item)
            model.beginRemoveRows(QModelIndex(), row_index, row_index)
            model._data.pop(row_index)
            model._selected.pop(selection_key, None)
            model.endRemoveRows()
            self._stat_updates = len(model._data)
            self.update_stats()
            self._refresh_update_filter_summary()
            return

"""Final integrity guards for scan-bound version-aware update behavior."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex

from src.ui.version_aware_window import VersionAwareMainWindow


class VersionIntegrityMainWindow(VersionAwareMainWindow):
    """Close lifecycle/identity races introduced by asynchronous version mapping."""

    def _handle_job_finished(self, name):
        """Restart deferred version reconciliation only after job ownership is released."""
        super()._handle_job_finished(name)
        if self._is_closing:
            return
        if name == "version-map" and self._version_reconcile_pending:
            self._version_reconcile_pending = False
            self._start_version_reconciliation(self._version_scan_generation)

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
            return

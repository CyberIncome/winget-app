"""Keep Winget authority and Detective information stable across refreshes.

The Updates table intentionally contains two classes of rows:

* current Winget-proven upgrades, which are actionable; and
* Detective-only observations, which are informational.

A Winget refresh must replace the authoritative Winget snapshot without making
informational Detective rows disappear merely because Detective was not rerun.
Likewise, the "Updates Available" statistic must always mean actionable,
Winget-proven updates rather than the mixed table row count.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex

from src.ui.startup_optimized_window import StartupOptimizedMainWindow


class AuthoritativeUpdatesMainWindow(StartupOptimizedMainWindow):
    """Preserve Detective rows while counting only authoritative Winget updates."""

    @staticmethod
    def _identity_values(item: dict) -> tuple[str, str]:
        return (
            str(item.get("Id") or "").strip().casefold(),
            str(item.get("Name") or "").strip().casefold(),
        )

    def _authoritative_update_count(self) -> int:
        model = self.proxy_model.sourceModel()
        if model is None:
            return 0
        return sum(
            1
            for item in getattr(model, "_data", [])
            if self._is_winget_update_item(item)
        )

    def _sync_authoritative_update_count(self) -> int:
        count = self._authoritative_update_count()
        self._stat_updates = count
        self.update_stats()
        return count

    def _detective_rows_snapshot(self) -> list[dict]:
        model = self.proxy_model.sourceModel()
        if model is None:
            return []
        return [
            dict(item)
            for item in getattr(model, "_data", [])
            if item.get("UpdateSource") == "detective"
        ]

    def _restore_detective_rows(self, detective_rows: list[dict]) -> int:
        """Restore only Detective rows not superseded by fresh Winget rows."""
        model = self.proxy_model.sourceModel()
        if model is None or not detective_rows:
            return 0

        occupied_ids = set()
        occupied_names = set()
        for item in getattr(model, "_data", []):
            item_id, name = self._identity_values(item)
            if item_id:
                occupied_ids.add(item_id)
            if name:
                occupied_names.add(name)

        additions = []
        for source_item in detective_rows:
            item = dict(source_item)
            item_id, name = self._identity_values(item)
            if (item_id and item_id in occupied_ids) or (
                name and name in occupied_names
            ):
                continue
            item["UpdateSource"] = "detective"
            item["Source"] = "detective"
            additions.append(item)
            if item_id:
                occupied_ids.add(item_id)
            if name:
                occupied_names.add(name)

        if not additions:
            return 0

        first = len(model._data)
        last = first + len(additions) - 1
        model.beginInsertRows(QModelIndex(), first, last)
        for item in additions:
            model._data.append(item)
            model._selected[model.selection_key_for_item(item)] = False
        model.endInsertRows()
        return len(additions)

    def apply_winget_results(self, data):
        """Refresh Winget rows while retaining independent Detective observations."""
        detective_rows = self._detective_rows_snapshot()
        result = super().apply_winget_results(data)
        restored = self._restore_detective_rows(detective_rows)
        authoritative = self._sync_authoritative_update_count()
        if restored:
            self.logger.info(
                "Preserved %d Detective informational row(s) across Winget refresh; "
                "authoritative_updates=%d",
                restored,
                authoritative,
            )
        return result

    def _detective_job_succeeded(self, results):
        """Allow Detective to enrich the table without inflating update count."""
        result = super()._detective_job_succeeded(results)
        authoritative = self._sync_authoritative_update_count()
        self.logger.info(
            "Detective enrichment complete; authoritative_updates=%d",
            authoritative,
        )
        return result

    def remove_package_from_model(self, package_ref):
        """Keep the statistic authoritative after a successful package removal."""
        result = super().remove_package_from_model(package_ref)
        self._sync_authoritative_update_count()
        return result

"""Compatibility exports for the legacy presentation/model implementation.

The substantial historical UI implementation lives in ``legacy_window`` so it
can remain import-compatible without being an executable bypass around the
production hardening layer. Run this module directly only through the canonical
``src.main`` entry point below.
"""

from PySide6.QtCore import QModelIndex, Qt

from src.logic.executor import (
    is_valid_app_id,
    validate_package_name,
    validate_source_name,
)
from src.ui.legacy_window import (
    ConsoleLogHandler,
    CustomSortProxy,
    GuiConsoleFilter,
    MainWindow,
    StatCard,
    UpdateModel as LegacyUpdateModel,
)


class UpdateModel(LegacyUpdateModel):
    """Flat table model with defensive indexes and safe package references."""

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if not 0 <= index.row() < len(self._data):
            return None
        if not 0 <= index.column() < len(self.headers):
            return None
        return super().data(index, role)

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        if not 0 <= index.row() < len(self._data):
            return False
        if not 0 <= index.column() < len(self.headers):
            return False
        return super().setData(index, value, role)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and not 0 <= section < len(self.headers):
            return None
        return super().headerData(section, orientation, role)

    def selection_key_for_item(self, item):
        """Return the selection identity for one row."""
        return item.get("Id") or item.get("Name")

    def get_selected_ids(self):
        """Return visible package identifiers/names for checked rows."""
        return [
            item.get("Id") or item.get("Name")
            for item in self._data
            if self._selected.get(self.selection_key_for_item(item), False)
        ]

    def _package_ref_for_item(self, item):
        """Return a validated exact Winget package reference or ``None``."""
        package_id = item.get("Id")
        if is_valid_app_id(package_id):
            ref = {"value": package_id, "match_by": "id"}
        else:
            try:
                package_name = validate_package_name(item.get("Name"))
            except ValueError:
                return None
            ref = {"value": package_name, "match_by": "name"}

        try:
            source = validate_source_name(item.get("Source"))
        except ValueError:
            return None
        if source:
            ref["source"] = source
        return ref

    def get_selected_packages(self):
        refs = []
        for item in self._data:
            if not self._selected.get(self.selection_key_for_item(item), False):
                continue
            ref = self._package_ref_for_item(item)
            if ref is not None:
                refs.append(ref)
        return refs

    def get_all_packages(self):
        refs = []
        for item in self._data:
            ref = self._package_ref_for_item(item)
            if ref is not None:
                refs.append(ref)
        return refs

    def package_refs_for_rows(self, rows):
        refs = []
        seen = set()
        for row in rows:
            if not 0 <= row < len(self._data):
                continue
            ref = self._package_ref_for_item(self._data[row])
            if ref is None:
                continue
            key = (
                ref["match_by"],
                ref["value"].lower(),
                str(ref.get("source") or "").lower(),
            )
            if key not in seen:
                refs.append(ref)
                seen.add(key)
        return refs


__all__ = [
    "ConsoleLogHandler",
    "CustomSortProxy",
    "GuiConsoleFilter",
    "MainWindow",
    "StatCard",
    "UpdateModel",
]


def main():
    """Route direct execution through the hardened production entry point."""
    from src.main import main as production_main

    return production_main()


if __name__ == "__main__":
    raise SystemExit(main())

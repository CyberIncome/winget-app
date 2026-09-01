"""Compatibility exports for the legacy presentation/model implementation.

The substantial historical UI implementation lives in ``legacy_window`` so it
can remain import-compatible without being an executable bypass around the
production hardening layer. Run this module directly only through the canonical
``src.main`` entry point below.
"""

from PySide6.QtCore import QModelIndex, Qt

from src.ui.legacy_window import (
    ConsoleLogHandler,
    CustomSortProxy,
    GuiConsoleFilter,
    MainWindow,
    StatCard,
    UpdateModel as LegacyUpdateModel,
)


class UpdateModel(LegacyUpdateModel):
    """Flat table model with defensive Qt index bounds."""

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

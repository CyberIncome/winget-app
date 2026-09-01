"""Compatibility exports for the legacy presentation/model implementation.

The substantial historical UI implementation lives in ``legacy_window`` so it
can remain import-compatible without being an executable bypass around the
production hardening layer. Run this module directly only through the canonical
``src.main`` entry point below.
"""

from src.ui.legacy_window import (
    ConsoleLogHandler,
    CustomSortProxy,
    GuiConsoleFilter,
    MainWindow,
    StatCard,
    UpdateModel,
)

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

#!/usr/bin/env python3
"""Create, show, and cleanly close the canonical runtime window without scans."""

from __future__ import annotations

from pathlib import Path
import sys


# Executing ``python scripts/smoke_gui.py`` makes ``scripts`` sys.path[0].
# Add the repository root explicitly before importing the application package so
# the smoke gate behaves the same whether it is launched from the repo root or
# by an absolute script path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from src.ui.runtime_window import RuntimeMainWindow


def main() -> int:
    """Exercise runtime Qt construction and shutdown on the local machine."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = RuntimeMainWindow()
    window.show()

    # MainWindow normally schedules startup after 500 ms. Close before that
    # deadline so this smoke test exercises Qt/Win32 construction + teardown
    # without invoking Winget, registry inventory, network, or detective work.
    QTimer.singleShot(200, window.close)
    QTimer.singleShot(350, app.quit)
    exit_code = app.exec()
    if not window._is_closing:
        raise RuntimeError("runtime window did not execute clean shutdown")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create, show, and cleanly close the production window without running scans."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from src.ui.production_window import ProductionMainWindow


def main() -> int:
    """Exercise production Qt construction and shutdown on the local machine."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = ProductionMainWindow()
    window.show()

    # MainWindow normally schedules startup after 500 ms. Close before that
    # deadline so this smoke test exercises Qt/Win32 construction + teardown
    # without invoking Winget, registry inventory, network, or detective work.
    QTimer.singleShot(200, window.close)
    QTimer.singleShot(350, app.quit)
    exit_code = app.exec()
    if not window._is_closing:
        raise RuntimeError("production window did not execute clean shutdown")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

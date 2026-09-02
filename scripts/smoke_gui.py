#!/usr/bin/env python3
"""Create, show, and cleanly close the canonical version-aware window."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from src.ui.version_aware_window import VersionAwareMainWindow


def main() -> int:
    """Exercise canonical product Qt construction and shutdown locally."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = VersionAwareMainWindow()
    window.show()

    # MainWindow normally schedules startup after 500 ms. Close before that
    # deadline so this smoke test exercises construction + teardown without
    # invoking Winget, registry inventory, network, or detective work.
    QTimer.singleShot(200, window.close)
    QTimer.singleShot(350, app.quit)
    exit_code = app.exec()
    if not window._is_closing:
        raise RuntimeError("version-aware window did not execute clean shutdown")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

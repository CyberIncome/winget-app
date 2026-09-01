"""Final production window compatibility layer."""

from PySide6.QtCore import QProcess, QTimer

from src.ui.hardened_window import HardenedMainWindow


class ProductionMainWindow(HardenedMainWindow):
    """Apply final Qt signal-order compatibility guards."""

    def handle_process_error(self, error):
        failed_to_start = (
            error == QProcess.FailedToStart
            or str(error).endswith("FailedToStart")
        )
        super().handle_process_error(error)
        if failed_to_start:
            # Qt reports FailedToStart through errorOccurred rather than a
            # normal child completion on common Windows builds. The legacy
            # guard is retained briefly in case a binding also delivers a
            # finished signal, then cleared before another queued update can
            # start so it can never poison the next process generation.
            QTimer.singleShot(50, self._clear_failed_start_guard)

    def _clear_failed_start_guard(self):
        self._process_start_failed = False

"""Final production window compatibility layer."""

from PySide6.QtCore import QProcess

from src.ui.hardened_window import HardenedMainWindow


class ProductionMainWindow(HardenedMainWindow):
    """Apply final Qt process-generation compatibility guards."""

    def __init__(self):
        self._failed_start_pending = False
        super().__init__()
        self.process.started.connect(self._handle_process_started)

    def handle_process_error(self, error):
        failed_to_start = (
            error == QProcess.FailedToStart
            or str(error).endswith("FailedToStart")
        )
        if failed_to_start:
            # Keep the failed generation marked until a later process actually
            # reaches Running. Qt normally does not emit finished() for a
            # process that never started, but this guard makes that assumption
            # non-destructive if a binding/platform behaves differently.
            self._failed_start_pending = True
        super().handle_process_error(error)

    def _handle_process_started(self):
        self._failed_start_pending = False
        self._process_start_failed = False

    def process_finished(self, code, status):
        if self._failed_start_pending:
            self.logger.warning(
                "Ignoring finished signal for a failed-to-start generation."
            )
            self._process_start_failed = False
            return
        super().process_finished(code, status)

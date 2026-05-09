import sys
import os
import logging
import faulthandler
import threading
import time
from multiprocessing import freeze_support
from src.logic.config import CONFIG_DIR

_BOOT_STARTED_AT = time.perf_counter()
_FAULT_LOG_STREAM = None


def _resolve_log_file():
    """Return a writable persistent log path."""
    candidates = [
        os.path.join(CONFIG_DIR, "logs"),
        os.path.join(
            os.getenv("LOCALAPPDATA", os.path.expanduser("~")),
            "WingetUniversalDashboard",
            "logs",
        ),
        os.getcwd(),
    ]
    for log_dir in candidates:
        try:
            os.makedirs(log_dir, exist_ok=True)
            return os.path.join(log_dir, "winget_gui.log")
        except OSError:
            continue
    return os.path.join(os.getcwd(), "winget_gui.log")


def _install_crash_hooks(log_file):
    """Capture unhandled Python and native crashes to persistent logs."""
    global _FAULT_LOG_STREAM

    crash_candidates = [
        os.path.join(os.path.dirname(log_file), "winget_crash.log"),
        os.path.join(
            os.path.dirname(log_file),
            f"winget_crash.{os.getpid()}.log",
        ),
        os.path.join(os.getcwd(), f"winget_crash.{os.getpid()}.log"),
    ]
    if _FAULT_LOG_STREAM is None:
        for crash_log in crash_candidates:
            try:
                os.makedirs(os.path.dirname(crash_log), exist_ok=True)
                _FAULT_LOG_STREAM = open(
                    crash_log, "a", encoding="utf-8"
                )
                faulthandler.enable(_FAULT_LOG_STREAM, all_threads=True)
                break
            except OSError:
                continue

    def _log_unhandled_exception(exc_type, exc_value, exc_traceback, source):
        logging.getLogger(__name__).critical(
            "Unhandled exception in %s",
            source,
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def _sys_hook(exc_type, exc_value, exc_traceback):
        _log_unhandled_exception(
            exc_type, exc_value, exc_traceback, "main thread"
        )

    def _thread_hook(args):
        _log_unhandled_exception(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            f"thread {args.thread.name}",
        )

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


def _create_log_handler(log_file):
    """Create a rotating log handler, falling back if the file is locked."""
    from logging.handlers import RotatingFileHandler

    candidates = [
        log_file,
        os.path.join(
            os.path.dirname(log_file),
            f"winget_gui.{os.getpid()}.log",
        ),
        os.path.join(os.getcwd(), f"winget_gui.{os.getpid()}.log"),
    ]
    last_error = None
    for candidate in candidates:
        try:
            os.makedirs(os.path.dirname(candidate), exist_ok=True)
            return (
                RotatingFileHandler(
                    candidate,
                    maxBytes=10 * 1024 * 1024,
                    backupCount=3,
                    encoding="utf-8",
                ),
                candidate,
            )
        except OSError as exc:
            last_error = exc
    raise last_error


def _configure_library_logging():
    """Reduce third-party debug noise in the persisted app log."""
    if os.getenv("WUD_VERBOSE_DEPS", "") == "1":
        return
    for logger_name in [
        "urllib3",
        "keyring",
        "win32ctypes",
    ]:
        logging.getLogger(logger_name).setLevel(logging.INFO)


def main():
    # Persist logs outside PyInstaller's temporary extraction directory.
    freeze_support()
    log_file = _resolve_log_file()
    handler, active_log_file = _create_log_handler(log_file)
    
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            handler,
            logging.StreamHandler(sys.stdout)
        ]
    )
    _configure_library_logging()

    _install_crash_hooks(log_file)

    logger = logging.getLogger(__name__)
    logger.info(
        "Starting WingetGui. Log file: %s. Boot %.3fs",
        active_log_file,
        time.perf_counter() - _BOOT_STARTED_AT,
    )

    from PySide6.QtWidgets import QApplication
    from src.ui.main_window import MainWindow

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    # Load Styles
    qss_path = os.path.join(os.path.dirname(__file__), "ui", "styles.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    
    # In CI or if specifically testing, we might not want to exec_()
    if "pytest" not in sys.modules:
        return app.exec()
    return 0

if __name__ == "__main__":
    sys.exit(main())

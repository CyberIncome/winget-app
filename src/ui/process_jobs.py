"""Qt-owned lifecycle wrapper for isolated multiprocessing jobs."""

from __future__ import annotations

import logging
import time
from multiprocessing import get_context
from queue import Empty
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal


class ManagedProcessJob(QObject):
    """Own one spawned child process and poll it from the Qt event loop."""

    succeeded = Signal(str, object)
    failed = Signal(str, str)
    finished = Signal(str)

    def __init__(
        self,
        name: str,
        target: Callable,
        args: tuple = (),
        timeout_seconds: float = 180.0,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.name = name
        self._target = target
        self._args = args
        self._timeout_seconds = timeout_seconds
        self._ctx = get_context("spawn")
        self._queue = None
        self._process = None
        self._started_at = 0.0
        self._done = False
        self._logger = logging.getLogger(__name__)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)

    @property
    def running(self) -> bool:
        return bool(
            not self._done
            and self._process is not None
            and self._process.is_alive()
        )

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    def start(self) -> bool:
        if self._process is not None:
            raise RuntimeError(f"Job {self.name!r} has already been started")
        try:
            self._queue = self._ctx.Queue(maxsize=1)
            self._process = self._ctx.Process(
                name=f"wud-{self.name}",
                target=self._target,
                args=(*self._args, self._queue),
            )
            self._process.start()
            self._started_at = time.monotonic()
            self._timer.start()
            self._logger.info(
                "JOB START name=%s pid=%s timeout=%ss",
                self.name,
                self.pid,
                self._timeout_seconds,
            )
            return True
        except Exception as exc:
            self._logger.exception("JOB START FAILED name=%s", self.name)
            self._finish_failure(f"Failed to start {self.name}: {exc}")
            return False

    def _poll(self) -> None:
        if self._done:
            return

        envelope = None
        if self._queue is not None:
            try:
                envelope = self._queue.get_nowait()
            except Empty:
                pass
            except (EOFError, OSError, ValueError) as exc:
                self._finish_failure(
                    f"{self.name} result queue failed: {exc}"
                )
                return

        if envelope is not None:
            if envelope.get("ok"):
                value = envelope.get("value")
                self._cleanup_process(grace_seconds=0.5)
                self._done = True
                self._logger.info("JOB SUCCESS name=%s", self.name)
                self.succeeded.emit(self.name, value)
                self.finished.emit(self.name)
                return
            detail = envelope.get("error") or "unknown worker error"
            trace = envelope.get("traceback")
            if trace:
                self._logger.error(
                    "JOB CHILD TRACE name=%s\n%s", self.name, trace
                )
            self._finish_failure(
                f"{self.name} failed "
                f"({envelope.get('error_type', 'Error')}): {detail}"
            )
            return

        elapsed = time.monotonic() - self._started_at
        if self._timeout_seconds > 0 and elapsed >= self._timeout_seconds:
            self._finish_failure(
                f"{self.name} timed out after "
                f"{self._timeout_seconds:.0f}s",
                terminate=True,
            )
            return

        if self._process is not None and not self._process.is_alive():
            exit_code = self._process.exitcode
            try:
                if self._queue is not None:
                    envelope = self._queue.get(timeout=0.05)
            except (Empty, EOFError, OSError, ValueError):
                envelope = None
            if envelope is not None:
                if envelope.get("ok"):
                    value = envelope.get("value")
                    self._cleanup_process()
                    self._done = True
                    self._logger.info(
                        "JOB SUCCESS name=%s", self.name
                    )
                    self.succeeded.emit(self.name, value)
                    self.finished.emit(self.name)
                    return
                detail = envelope.get("error") or "unknown worker error"
                self._finish_failure(
                    f"{self.name} failed: {detail}"
                )
                return
            self._finish_failure(
                f"{self.name} exited without a result "
                f"(exit code {exit_code})"
            )

    def cancel(self, reason: str = "cancelled") -> None:
        if self._done:
            return
        self._logger.info(
            "JOB CANCEL name=%s reason=%s", self.name, reason
        )
        self._timer.stop()
        self._cleanup_process(terminate=True)
        self._done = True

    def _finish_failure(self, message: str, terminate: bool = False) -> None:
        if self._done:
            return
        self._timer.stop()
        self._cleanup_process(terminate=terminate)
        self._done = True
        self._logger.error(
            "JOB FAILED name=%s detail=%s", self.name, message
        )
        self.failed.emit(self.name, message)
        self.finished.emit(self.name)

    def _cleanup_process(
        self,
        terminate: bool = False,
        grace_seconds: float = 0.2,
    ) -> None:
        self._timer.stop()
        process = self._process
        if process is not None:
            # Process.start itself can fail. An unstarted Process has no pid
            # and Python raises AssertionError if it is joined/is_alive.
            if process.pid is not None:
                if terminate and process.is_alive():
                    process.terminate()
                process.join(timeout=grace_seconds)
                if process.is_alive():
                    self._logger.warning(
                        "JOB FORCE KILL name=%s pid=%s",
                        self.name,
                        process.pid,
                    )
                    process.kill()
                    process.join(timeout=1.0)
                try:
                    process.close()
                except (OSError, ValueError):
                    pass
            self._process = None

        queue = self._queue
        if queue is not None:
            try:
                queue.close()
            except (OSError, ValueError):
                pass
            try:
                queue.cancel_join_thread()
            except (AttributeError, OSError, ValueError):
                pass
            self._queue = None

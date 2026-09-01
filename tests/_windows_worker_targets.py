"""Pickle-safe worker targets for local Windows multiprocessing verification."""

from __future__ import annotations

import os
import time


def succeed(value, result_queue) -> None:
    """Return one successful ManagedProcessJob envelope."""
    result_queue.put({"ok": True, "value": value})


def sleep_then_succeed(seconds, result_queue) -> None:
    """Stay alive long enough for timeout/cancellation tests."""
    time.sleep(seconds)
    result_queue.put({"ok": True, "value": "finished"})


def exit_without_result(code, result_queue) -> None:
    """Exit abruptly without writing the expected queue envelope."""
    del result_queue
    os._exit(code)

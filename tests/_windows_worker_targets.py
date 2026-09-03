"""Pickle-safe worker targets for local Windows multiprocessing verification."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time


def succeed(value, result_queue) -> None:
    """Return one successful ManagedProcessJob envelope."""
    result_queue.put({"ok": True, "value": value})


def sleep_then_succeed(seconds, result_queue) -> None:
    """Stay alive long enough for timeout/cancellation tests."""
    time.sleep(seconds)
    result_queue.put({"ok": True, "value": "finished"})


def spawn_grandchild_then_sleep(sentinel_path, seconds, result_queue) -> None:
    """Spawn a delayed grandchild so cancellation can prove tree containment."""
    sentinel = str(Path(sentinel_path))
    child_code = (
        "import pathlib,time; "
        "time.sleep(1.0); "
        f"pathlib.Path({sentinel!r}).write_text('survived', encoding='utf-8')"
    )
    subprocess.Popen([sys.executable, "-c", child_code])
    time.sleep(seconds)
    result_queue.put({"ok": True, "value": "worker-finished"})


def exit_without_result(code, result_queue) -> None:
    """Exit abruptly without writing the expected queue envelope."""
    del result_queue
    os._exit(code)

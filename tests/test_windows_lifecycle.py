"""Native Windows lifecycle acceptance tests.

These tests are skipped off Windows. They intentionally exercise real
multiprocessing ``spawn`` and QProcess behavior while using only Python child
processes; they never install, remove, or update packages.
"""

from __future__ import annotations

import os
import sys
import time
from collections import deque

import pytest
from PySide6.QtCore import QProcess

from src.ui.process_jobs import ManagedProcessJob
from src.ui.production_window import ProductionMainWindow
from tests._windows_worker_targets import (
    exit_without_result,
    sleep_then_succeed,
    succeed,
)


pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="native Windows lifecycle acceptance",
)


def _make_window(qtbot, monkeypatch):
    # Pytest already suppresses the legacy deferred startup timer, but keep
    # this explicit so the integration tests cannot begin a real Winget scan.
    monkeypatch.setattr(
        ProductionMainWindow,
        "startup_sequence",
        lambda self: None,
    )
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    return window


def test_managed_spawn_success_cleans_process_and_queue(qtbot):
    job = ManagedProcessJob(
        "windows-spawn-success",
        succeed,
        args=("ok",),
        timeout_seconds=5,
    )

    with qtbot.waitSignal(job.succeeded, timeout=10_000) as signal:
        assert job.start() is True

    assert signal.args == ["windows-spawn-success", "ok"]
    assert job.running is False
    assert job._process is None
    assert job._queue is None


def test_managed_spawn_cancel_joins_child(qtbot):
    job = ManagedProcessJob(
        "windows-spawn-cancel",
        sleep_then_succeed,
        args=(30,),
        timeout_seconds=60,
    )
    assert job.start() is True
    qtbot.waitUntil(lambda: job.running, timeout=10_000)

    with qtbot.waitSignal(job.finished, timeout=10_000):
        job.cancel("integration test")

    assert job.running is False
    assert job._process is None
    assert job._queue is None


def test_managed_spawn_timeout_terminates_child(qtbot):
    job = ManagedProcessJob(
        "windows-spawn-timeout",
        sleep_then_succeed,
        args=(30,),
        timeout_seconds=0.2,
    )

    with qtbot.waitSignal(job.failed, timeout=10_000) as signal:
        assert job.start() is True

    assert "timed out" in signal.args[1].lower()
    assert job.running is False
    assert job._process is None
    assert job._queue is None


def test_managed_spawn_exit_without_result_fails_closed(qtbot):
    job = ManagedProcessJob(
        "windows-spawn-abrupt-exit",
        exit_without_result,
        args=(17,),
        timeout_seconds=5,
    )

    with qtbot.waitSignal(job.failed, timeout=10_000) as signal:
        assert job.start() is True

    assert "exited without a result" in signal.args[1]
    assert "17" in signal.args[1]
    assert job._process is None
    assert job._queue is None


def test_qprocess_failed_to_start_then_valid_generation_recovers(
    qtbot, monkeypatch
):
    window = _make_window(qtbot, monkeypatch)
    window.current_operation = "update"
    window.set_ui_busy("Updating apps...", True, "update")
    window.process_queue = deque(
        [{"value": "Never.Runs", "match_by": "id", "silent": True}]
    )

    missing = f"wud-missing-{time.monotonic_ns()}.exe"
    with qtbot.waitSignal(window.process.errorOccurred, timeout=10_000):
        window.process.start(missing, [])

    qtbot.waitUntil(
        lambda: window.current_operation is None,
        timeout=5_000,
    )
    assert list(window.process_queue) == []
    assert "update" not in window._active_tasks
    assert window._failed_start_pending is True

    with qtbot.waitSignal(window.process.started, timeout=10_000):
        window.process.start(
            sys.executable,
            ["-c", "import time; print('generation recovered'); time.sleep(0.5)"],
        )
    assert window._failed_start_pending is False

    with qtbot.waitSignal(window.process.finished, timeout=10_000):
        pass


def test_qprocess_kill_is_crash_and_never_silent_retry(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    window.current_operation = "update"
    window.set_ui_busy("Updating apps...", True, "update")
    window.current_package_ref = {
        "value": "Synthetic.Package",
        "match_by": "id",
        "source": "winget",
        "silent": True,
    }
    window.process_queue = deque()

    with qtbot.waitSignal(window.process.started, timeout=10_000):
        window.process.start(
            sys.executable,
            ["-c", "import time; time.sleep(30)"],
        )
    window.start_process_watchdog(timeout=60, idle_warning=30)

    with qtbot.waitSignal(window.process.finished, timeout=10_000) as signal:
        window.process.kill()

    assert signal.args[1] == QProcess.CrashExit
    assert list(window.process_queue) == []
    assert window.current_operation is None
    assert "update" not in window._active_tasks


def test_watchdog_hard_timeout_kills_without_retry(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    window.current_operation = "update"
    window.set_ui_busy("Updating apps...", True, "update")
    window.current_package_ref = {
        "value": "Synthetic.Timeout",
        "match_by": "id",
        "source": "winget",
        "silent": True,
    }
    window.process_queue = deque()

    with qtbot.waitSignal(window.process.started, timeout=10_000):
        window.process.start(
            sys.executable,
            ["-c", "import time; time.sleep(30)"],
        )

    window.start_process_watchdog(timeout=0.1, idle_warning=0.05)
    window._process_started_at = time.monotonic() - 1

    with qtbot.waitSignal(window.process.finished, timeout=10_000):
        window.check_process_timeout()

    assert list(window.process_queue) == []
    assert window.current_operation is None
    assert "update" not in window._active_tasks


def test_window_close_cancels_owned_spawned_job(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    started = window._start_job(
        "integration-close",
        sleep_then_succeed,
        args=(30,),
        timeout=60,
    )
    assert started is True

    job = window._managed_jobs["integration-close"]
    qtbot.waitUntil(lambda: job.running, timeout=10_000)

    window.close()

    assert window._is_closing is True
    assert window._managed_jobs == {}
    assert job.running is False
    assert job._process is None
    assert job._queue is None

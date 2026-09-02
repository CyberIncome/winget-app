from __future__ import annotations

import os
import sys
import time

import pytest

from src.logic.command_runner import run_command
from src.ui.process_jobs import ManagedProcessJob
from tests._windows_worker_targets import spawn_grandchild_then_sleep


pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="native Windows Job Object containment",
)


def test_required_job_containment_kills_lingering_grandchild(tmp_path):
    sentinel = tmp_path / "grandchild-survived.txt"
    child_code = (
        "import pathlib,time; "
        "time.sleep(1.0); "
        f"pathlib.Path({str(sentinel)!r}).write_text('survived', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(0.2); "
        "print('parent exiting')"
    )

    result = run_command(
        [sys.executable, "-c", parent_code],
        timeout=5,
        require_process_tree_containment=True,
    )

    assert result.ok is True, result.failure_summary()
    assert "parent exiting" in result.stdout
    time.sleep(1.5)
    assert not sentinel.exists(), (
        "grandchild survived after the kill-on-close Job Object handle was released"
    )


def test_required_job_containment_allows_normal_command():
    result = run_command(
        [sys.executable, "-c", "import time; time.sleep(0.1); print('contained')"],
        timeout=5,
        require_process_tree_containment=True,
    )
    assert result.ok is True, result.failure_summary()
    assert result.stdout.strip() == "contained"


def test_managed_worker_cancel_kills_inherited_grandchild(qtbot, tmp_path):
    sentinel = tmp_path / "managed-grandchild-survived.txt"
    job = ManagedProcessJob(
        "managed-tree-containment",
        spawn_grandchild_then_sleep,
        args=(str(sentinel), 30),
        timeout_seconds=60,
    )
    assert job.start() is True
    qtbot.waitUntil(lambda: job.running, timeout=10_000)

    # Give the worker enough time to enter its Job Object and spawn the delayed
    # grandchild, but cancel before that grandchild reaches its one-second write.
    qtbot.wait(300)
    with qtbot.waitSignal(job.finished, timeout=10_000):
        job.cancel("tree-containment integration test")

    assert job.running is False
    assert job._process is None
    assert job._queue is None
    qtbot.wait(1_200)
    assert not sentinel.exists(), (
        "grandchild survived after its managed worker was cancelled"
    )

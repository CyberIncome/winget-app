"""Regression tests for exception-contained managed process cleanup."""

from __future__ import annotations

import src.ui.process_jobs as process_jobs
from src.logic.windows_job import WindowsKillOnCloseJob
from src.ui.process_jobs import ManagedProcessJob


class HostileProcess:
    pid = 4242

    def __init__(self):
        self.alive_calls = 0
        self.terminate_calls = 0
        self.kill_calls = 0
        self.close_calls = 0

    @property
    def exitcode(self):
        raise ValueError("exitcode unavailable")

    def is_alive(self):
        self.alive_calls += 1
        if self.alive_calls == 1:
            return True
        if self.alive_calls == 2:
            raise OSError("handle raced")
        return True

    def terminate(self):
        self.terminate_calls += 1
        raise OSError("terminate failed")

    def join(self, timeout=None):
        raise AssertionError("join failed")

    def kill(self):
        self.kill_calls += 1
        raise OSError("kill failed")

    def close(self):
        self.close_calls += 1
        raise ValueError("close failed")


class HostileQueue:
    def __init__(self):
        self.close_calls = 0
        self.cancel_calls = 0

    def close(self):
        self.close_calls += 1
        raise OSError("queue close failed")

    def cancel_join_thread(self):
        self.cancel_calls += 1
        raise ValueError("queue cancel failed")


class EnvelopeQueue:
    def __init__(self):
        self.values = []

    def put(self, value):
        self.values.append(value)


def test_cleanup_contains_process_and_queue_state_errors(qtbot):
    job = ManagedProcessJob("hostile-cleanup", lambda queue: None)
    process = HostileProcess()
    queue = HostileQueue()
    job._process = process
    job._queue = queue

    job._cleanup_process(terminate=True, grace_seconds=0)

    assert job._process is None
    assert job._queue is None
    assert process.terminate_calls >= 2
    assert process.kill_calls == 1
    assert process.close_calls == 1
    assert queue.close_calls == 1
    assert queue.cancel_calls == 1


def test_invalid_worker_envelope_fails_closed(qtbot):
    job = ManagedProcessJob("invalid-envelope", lambda queue: None)

    with qtbot.waitSignal(job.failed, timeout=1000) as failed:
        job._consume_envelope(["not", "a", "mapping"])

    assert "invalid result envelope" in failed.args[1]
    assert job._done is True


def test_worker_entry_reports_containment_failure_without_running_target(monkeypatch):
    queue = EnvelopeQueue()
    target_calls = []

    monkeypatch.setattr(process_jobs.os, "name", "nt")

    def fail_containment():
        raise OSError("synthetic containment failure")

    monkeypatch.setattr(
        WindowsKillOnCloseJob,
        "attach_current_process",
        fail_containment,
    )

    process_jobs._managed_process_entry(
        lambda result_queue: target_calls.append(result_queue),
        (),
        queue,
    )

    assert target_calls == []
    assert len(queue.values) == 1
    envelope = queue.values[0]
    assert envelope["ok"] is False
    assert envelope["error_type"] == "OSError"
    assert "synthetic containment failure" in envelope["error"]

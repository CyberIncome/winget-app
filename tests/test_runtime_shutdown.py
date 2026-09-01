"""Regression tests for the canonical runtime shutdown boundary."""

from __future__ import annotations

from src.ui.runtime_window import RuntimeMainWindow


class HostileQProcess:
    def __init__(self):
        self.state_calls = 0
        self.terminate_calls = 0
        self.wait_calls = 0
        self.kill_calls = 0

    def state(self):
        self.state_calls += 1
        raise RuntimeError("state wrapper invalid")

    def terminate(self):
        self.terminate_calls += 1
        raise RuntimeError("terminate handle raced")

    def waitForFinished(self, _timeout):
        self.wait_calls += 1
        raise RuntimeError("wait handle raced")

    def kill(self):
        self.kill_calls += 1
        raise RuntimeError("kill handle raced")


def test_runtime_close_contains_all_qprocess_teardown_errors(qtbot, monkeypatch):
    monkeypatch.setattr(RuntimeMainWindow, "startup_sequence", lambda self: None)
    window = RuntimeMainWindow()
    qtbot.addWidget(window)
    hostile = HostileQProcess()
    window.process = hostile

    window.close()

    assert window._is_closing is True
    assert hostile.state_calls == 1
    assert hostile.terminate_calls == 1
    assert hostile.wait_calls == 2
    assert hostile.kill_calls == 1


def test_runtime_qprocess_shutdown_stops_after_successful_wait(qtbot, monkeypatch):
    monkeypatch.setattr(RuntimeMainWindow, "startup_sequence", lambda self: None)
    window = RuntimeMainWindow()
    qtbot.addWidget(window)

    class GracefulQProcess:
        def __init__(self):
            self.kill_calls = 0

        def state(self):
            return 1  # any non-NotRunning state

        def terminate(self):
            return None

        def waitForFinished(self, _timeout):
            return True

        def kill(self):
            self.kill_calls += 1

    process = GracefulQProcess()
    window.process = process
    window.close()

    assert window._is_closing is True
    assert process.kill_calls == 0

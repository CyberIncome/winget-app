"""Regression tests for the canonical runtime process/shutdown boundary."""

from __future__ import annotations

from src.ui.production_window import ProductionMainWindow
from src.ui.runtime_window import RuntimeMainWindow


class HostileQProcess:
    def __init__(self):
        self.state_calls = 0
        self.terminate_calls = 0
        self.wait_calls = 0
        self.kill_calls = 0

    def state(self):
        self.state_calls += 1
        raise OSError("state wrapper invalid")

    def terminate(self):
        self.terminate_calls += 1
        raise ValueError("terminate handle raced")

    def waitForFinished(self, _timeout):
        self.wait_calls += 1
        raise RuntimeError("wait handle raced")

    def kill(self):
        self.kill_calls += 1
        raise LookupError("kill wrapper invalid")


def _window(qtbot, monkeypatch):
    monkeypatch.setattr(RuntimeMainWindow, "startup_sequence", lambda self: None)
    window = RuntimeMainWindow()
    qtbot.addWidget(window)
    return window


def test_runtime_close_contains_all_qprocess_teardown_errors(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)
    hostile = HostileQProcess()
    window.process = hostile

    window.close()

    assert window._is_closing is True
    assert hostile.state_calls == 1
    assert hostile.terminate_calls == 1
    assert hostile.wait_calls == 2
    assert hostile.kill_calls == 1


def test_runtime_qprocess_shutdown_stops_after_successful_wait(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)

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


def _assert_synchronous_boundary_recovery(
    window, monkeypatch, method_name, operation, call
):
    stopped = []
    recovered = []

    def explode(*_args, **_kwargs):
        raise RuntimeError(f"{method_name} exploded")

    monkeypatch.setattr(ProductionMainWindow, method_name, explode)
    monkeypatch.setattr(
        window, "_stop_qprocess_safely", lambda: stopped.append(True)
    )
    monkeypatch.setattr(
        window,
        "_recover_process_callback_failure",
        lambda op, boundary, exc: recovered.append(
            (op, boundary, str(exc))
        ),
    )

    call()

    assert stopped == [True]
    assert recovered == [
        (operation, method_name.replace("_updates", "-start").replace("_update", "-start"), f"{method_name} exploded")
    ] if method_name in {"refresh_updates", "batch_update"} else recovered
    return recovered


def test_runtime_refresh_start_exception_is_contained(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)
    stopped = []
    recovered = []
    monkeypatch.setattr(
        ProductionMainWindow,
        "refresh_updates",
        lambda self: (_ for _ in ()).throw(RuntimeError("refresh exploded")),
    )
    monkeypatch.setattr(
        window, "_stop_qprocess_safely", lambda: stopped.append(True)
    )
    monkeypatch.setattr(
        window,
        "_recover_process_callback_failure",
        lambda op, boundary, exc: recovered.append((op, boundary, str(exc))),
    )

    window.refresh_updates()

    assert stopped == [True]
    assert recovered == [("refresh", "refresh-start", "refresh exploded")]


def test_runtime_batch_start_exception_is_contained(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)
    stopped = []
    recovered = []
    monkeypatch.setattr(
        ProductionMainWindow,
        "batch_update",
        lambda self, refs: (_ for _ in ()).throw(RuntimeError("batch exploded")),
    )
    monkeypatch.setattr(
        window, "_stop_qprocess_safely", lambda: stopped.append(True)
    )
    monkeypatch.setattr(
        window,
        "_recover_process_callback_failure",
        lambda op, boundary, exc: recovered.append((op, boundary, str(exc))),
    )

    window.batch_update([{"value": "Example.App", "match_by": "id"}])

    assert stopped == [True]
    assert recovered == [("update", "batch-start", "batch exploded")]


def test_runtime_watchdog_exception_is_contained(qtbot, monkeypatch):
    window = _window(qtbot, monkeypatch)
    window.current_operation = "update"
    stopped = []
    recovered = []
    monkeypatch.setattr(
        ProductionMainWindow,
        "check_process_timeout",
        lambda self: (_ for _ in ()).throw(RuntimeError("watchdog exploded")),
    )
    monkeypatch.setattr(
        window, "_stop_qprocess_safely", lambda: stopped.append(True)
    )
    monkeypatch.setattr(
        window,
        "_recover_process_callback_failure",
        lambda op, boundary, exc: recovered.append((op, boundary, str(exc))),
    )

    window.check_process_timeout()

    assert stopped == [True]
    assert recovered == [("update", "watchdog", "watchdog exploded")]

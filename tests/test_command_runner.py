import sys

from src.logic.command_runner import run_command


def test_command_result_success():
    result = run_command(
        [sys.executable, "-c", "print('ok')"], timeout=5
    )
    assert result.ok
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
    assert result.failure_summary() == "success"


def test_command_result_nonzero_keeps_stderr():
    result = run_command(
        [
            sys.executable,
            "-c",
            "import sys; print('bad', file=sys.stderr); raise SystemExit(7)",
        ],
        timeout=5,
    )
    assert not result.ok
    assert result.returncode == 7
    assert "bad" in result.stderr
    assert "exited with code 7" in result.failure_summary()


def test_command_result_timeout_is_not_empty_success():
    result = run_command(
        [sys.executable, "-c", "import time; time.sleep(1)"],
        timeout=0.05,
    )
    assert not result.ok
    assert result.timed_out
    assert result.returncode is None
    assert result.failure_summary() == "timed out"


def test_command_result_start_failure_is_explicit():
    result = run_command(["definitely-not-a-real-command-wud"])
    assert not result.ok
    assert result.start_error
    assert result.returncode is None
    assert result.failure_summary().startswith("failed to start:")

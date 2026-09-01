import codecs
import sys

import src.logic.command_runner as command_runner
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


def test_command_runner_forces_wide_columns_by_default():
    result = run_command(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('COLUMNS', ''))",
        ],
        timeout=5,
    )
    assert result.ok
    assert result.stdout.strip() == "300"


def test_command_runner_allows_explicit_columns_override():
    result = run_command(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('COLUMNS', ''))",
        ],
        timeout=5,
        environment={"COLUMNS": "512"},
    )
    assert result.ok
    assert result.stdout.strip() == "512"


def test_command_runner_decodes_utf16_output_after_capture():
    text = "Name Id Version Available Source\n日本語 App"
    payload = codecs.BOM_UTF16_LE + text.encode("utf-16-le")
    script = (
        "import sys; "
        f"sys.stdout.buffer.write({payload!r}); "
        "sys.stdout.buffer.flush()"
    )

    result = run_command([sys.executable, "-c", script], timeout=5)

    assert result.ok
    assert result.stdout == text


def test_command_runner_decodes_nonzero_stderr_bytes():
    text = "エラー"
    payload = codecs.BOM_UTF16_LE + text.encode("utf-16-le")
    script = (
        "import sys; "
        f"sys.stderr.buffer.write({payload!r}); "
        "sys.stderr.buffer.flush(); "
        "raise SystemExit(9)"
    )

    result = run_command([sys.executable, "-c", script], timeout=5)

    assert result.returncode == 9
    assert result.stderr == text
    assert text in result.failure_summary()


def test_command_runner_rejects_oversized_stdout(monkeypatch):
    monkeypatch.setattr(command_runner, "MAX_CAPTURE_BYTES", 64)
    script = "import sys; sys.stdout.write('x' * 256); sys.stdout.flush()"

    result = run_command([sys.executable, "-c", script], timeout=5)

    assert result.returncode == 0
    assert result.output_overflow is True
    assert result.ok is False
    assert len(result.stdout) == 64
    assert "output exceeded 64 byte safety limit" == result.failure_summary()


def test_command_runner_rejects_oversized_stderr(monkeypatch):
    monkeypatch.setattr(command_runner, "MAX_CAPTURE_BYTES", 64)
    script = (
        "import sys; sys.stderr.write('e' * 256); "
        "sys.stderr.flush(); raise SystemExit(7)"
    )

    result = run_command([sys.executable, "-c", script], timeout=5)

    assert result.returncode == 7
    assert result.output_overflow is True
    assert result.ok is False
    assert len(result.stderr) == 64
    assert "output exceeded 64 byte safety limit" == result.failure_summary()

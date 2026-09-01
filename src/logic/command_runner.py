"""Structured subprocess execution shared by non-interactive CLI operations."""

from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
import tempfile
from typing import Mapping, Sequence

from src.logic.output_decode import decode_process_bytes


MAX_CAPTURE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a subprocess without conflating failure with empty output."""

    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    start_error: str | None = None
    output_overflow: bool = False

    @property
    def ok(self) -> bool:
        return (
            not self.timed_out
            and self.start_error is None
            and not self.output_overflow
            and self.returncode == 0
        )

    def failure_summary(self) -> str:
        if self.start_error:
            return f"failed to start: {self.start_error}"
        if self.timed_out:
            return "timed out"
        if self.output_overflow:
            return f"output exceeded {MAX_CAPTURE_BYTES} byte safety limit"
        if self.returncode != 0:
            detail = self.stderr.strip() or self.stdout.strip()
            if len(detail) > 4000:
                detail = detail[:4000] + "..."
            suffix = f": {detail}" if detail else ""
            return f"exited with code {self.returncode}{suffix}"
        return "success"


def _read_capture(file_handle, max_bytes: int) -> tuple[str, bool]:
    """Decode at most ``max_bytes`` from a disk-backed capture file."""
    file_handle.flush()
    try:
        size = os.fstat(file_handle.fileno()).st_size
    except OSError:
        size = max_bytes + 1
    file_handle.seek(0)
    raw = file_handle.read(max_bytes + 1)
    overflow = size > max_bytes or len(raw) > max_bytes
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    return decode_process_bytes(raw), overflow


def _stop_timed_out_process(process) -> None:
    """Best-effort bounded stop for a non-interactive timed-out child."""
    try:
        process.kill()
    except (OSError, ValueError):
        pass
    try:
        process.wait(timeout=5)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


def run_command(
    command: Sequence[str],
    timeout: float = 300,
    environment: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run a command and return a structured, locale-aware bounded outcome.

    Output is written to temporary files rather than unbounded Python pipes.
    After the child exits, at most ``MAX_CAPTURE_BYTES`` per stream is decoded.
    Oversized output is an explicit failed result so a truncated WinGet table
    can never be mistaken for an authoritative scan.

    WinGet formats its tabular output using the console width. Force a wide
    ``COLUMNS`` value unless the caller explicitly supplies another one so the
    CLI receives the same non-truncated protocol surface as the GUI.
    """
    normalized = tuple(str(part) for part in command)
    process_environment = os.environ.copy()
    if environment:
        process_environment.update(
            {str(key): str(value) for key, value in environment.items()}
        )
    if environment is None or "COLUMNS" not in environment:
        process_environment["COLUMNS"] = "300"

    try:
        with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(
            mode="w+b"
        ) as stderr_file:
            process = subprocess.Popen(
                normalized,
                stdout=stdout_file,
                stderr=stderr_file,
                env=process_environment,
            )
            timed_out = False
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _stop_timed_out_process(process)
                returncode = process.poll()

            stdout, stdout_overflow = _read_capture(
                stdout_file, MAX_CAPTURE_BYTES
            )
            stderr, stderr_overflow = _read_capture(
                stderr_file, MAX_CAPTURE_BYTES
            )
            return CommandResult(
                command=normalized,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                output_overflow=stdout_overflow or stderr_overflow,
            )
    except OSError as exc:
        return CommandResult(
            command=normalized,
            returncode=None,
            stdout="",
            stderr="",
            start_error=str(exc),
        )

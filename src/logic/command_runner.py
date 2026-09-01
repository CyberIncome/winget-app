"""Structured subprocess execution shared by non-interactive CLI operations."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Sequence


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a subprocess without conflating failure with empty output."""

    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    start_error: str | None = None

    @property
    def ok(self) -> bool:
        return (
            not self.timed_out
            and self.start_error is None
            and self.returncode == 0
        )

    def failure_summary(self) -> str:
        if self.start_error:
            return f"failed to start: {self.start_error}"
        if self.timed_out:
            return "timed out"
        if self.returncode != 0:
            detail = self.stderr.strip() or self.stdout.strip()
            suffix = f": {detail}" if detail else ""
            return f"exited with code {self.returncode}{suffix}"
        return "success"


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_command(
    command: Sequence[str], timeout: float = 300
) -> CommandResult:
    """Run a command and return a lossless structured outcome."""
    normalized = tuple(str(part) for part in command)
    try:
        completed = subprocess.run(
            normalized,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return CommandResult(
            command=normalized,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=normalized,
            returncode=None,
            stdout=_text(exc.stdout),
            stderr=_text(exc.stderr),
            timed_out=True,
        )
    except OSError as exc:
        return CommandResult(
            command=normalized,
            returncode=None,
            stdout="",
            stderr="",
            start_error=str(exc),
        )

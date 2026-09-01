"""Structured subprocess execution shared by non-interactive CLI operations."""

from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
from typing import Mapping, Sequence


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
    command: Sequence[str],
    timeout: float = 300,
    environment: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run a command and return a lossless structured outcome.

    WinGet formats its tabular output using the console width.  Force a wide
    ``COLUMNS`` value unless the caller explicitly supplies another one so the
    CLI receives the same non-truncated protocol surface as the GUI.
    """
    normalized = tuple(str(part) for part in command)
    process_environment = os.environ.copy()
    if environment:
        process_environment.update(
            {str(key): str(value) for key, value in environment.items()}
        )
    process_environment.setdefault("COLUMNS", "300")
    # An inherited COLUMNS value can be narrow.  For this app's command runner
    # the stable table contract is more important than preserving terminal UI.
    if environment is None or "COLUMNS" not in environment:
        process_environment["COLUMNS"] = "300"

    try:
        completed = subprocess.run(
            normalized,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=process_environment,
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

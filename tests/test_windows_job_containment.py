from __future__ import annotations

import os
from pathlib import Path
import sys
import time

import pytest

from src.logic.command_runner import run_command


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
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
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
        [sys.executable, "-c", "print('contained')"],
        timeout=5,
        require_process_tree_containment=True,
    )
    assert result.ok is True, result.failure_summary()
    assert result.stdout.strip() == "contained"

"""Offline source invariants for the production hardening layer."""

from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1]
HARDENED = ROOT / "src" / "ui" / "hardened_window.py"
JOBS = ROOT / "src" / "ui" / "process_jobs.py"


def test_hardened_window_has_no_raw_thread_launches():
    source = HARDENED.read_text(encoding="utf-8")
    assert "threading.Thread" not in source
    assert "daemon=True" not in source


def test_managed_job_has_bounded_terminate_and_kill_cleanup():
    source = JOBS.read_text(encoding="utf-8")
    assert "process.terminate()" in source
    assert "process.kill()" in source
    assert "process.join(timeout=" in source
    assert "queue.close()" in source


def test_changed_python_sources_parse_as_ast():
    for path in [
        HARDENED,
        JOBS,
        ROOT / "src" / "logic" / "worker_jobs.py",
    ]:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

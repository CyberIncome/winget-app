"""Offline source invariants for the production hardening layer."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDENED = ROOT / "src" / "ui" / "hardened_window.py"
JOBS = ROOT / "src" / "ui" / "process_jobs.py"
MAIN_SHIM = ROOT / "src" / "ui" / "main_window.py"
LEGACY = ROOT / "src" / "ui" / "legacy_window.py"


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
        MAIN_SHIM,
        LEGACY,
        ROOT / "src" / "logic" / "worker_jobs.py",
        ROOT / "src" / "ui" / "production_window.py",
    ]:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_production_entrypoint_uses_hardened_window():
    main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert "ProductionMainWindow" in main_source
    assert "window = ProductionMainWindow()" in main_source


def test_main_window_direct_execution_routes_to_canonical_main():
    source = MAIN_SHIM.read_text(encoding="utf-8")
    assert "from src.ui.legacy_window import" in source
    assert "from src.main import main as production_main" in source
    assert "raise SystemExit(main())" in source
    assert "window = MainWindow()" not in source


def test_failed_start_guard_clears_only_after_a_process_starts():
    source = (ROOT / "src" / "ui" / "production_window.py").read_text(
        encoding="utf-8"
    )
    assert "self.process.started.connect" in source
    assert "self._failed_start_pending = True" in source
    assert "self._failed_start_pending = False" in source
    assert "QTimer.singleShot" in source  # update queue scheduling remains bounded

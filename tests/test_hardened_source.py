"""Offline source invariants for the production hardening layers."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDENED = ROOT / "src" / "ui" / "hardened_window.py"
PRODUCTION = ROOT / "src" / "ui" / "production_window.py"
RUNTIME = ROOT / "src" / "ui" / "runtime_window.py"
JOBS = ROOT / "src" / "ui" / "process_jobs.py"
MAIN_SHIM = ROOT / "src" / "ui" / "main_window.py"
LEGACY = ROOT / "src" / "ui" / "legacy_window.py"
PARSER_FACADE = ROOT / "src" / "logic" / "parser.py"
LEGACY_PARSER = ROOT / "src" / "logic" / "legacy_parser.py"
SMOKE_GUI = ROOT / "scripts" / "smoke_gui.py"


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
        PRODUCTION,
        RUNTIME,
        JOBS,
        MAIN_SHIM,
        LEGACY,
        PARSER_FACADE,
        LEGACY_PARSER,
        ROOT / "src" / "logic" / "worker_jobs.py",
        ROOT / "src" / "logic" / "upgrade_parser.py",
        ROOT / "src" / "logic" / "output_decode.py",
        ROOT / "scripts" / "verify_windows.py",
        ROOT / "scripts" / "build_windows.py",
        SMOKE_GUI,
    ]:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_canonical_entrypoint_uses_runtime_shutdown_owner():
    main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    runtime_source = RUNTIME.read_text(encoding="utf-8")
    production_source = PRODUCTION.read_text(encoding="utf-8")
    hardened_source = HARDENED.read_text(encoding="utf-8")

    assert "from src.ui.runtime_window import RuntimeMainWindow" in main_source
    assert "window = RuntimeMainWindow()" in main_source
    assert "class RuntimeMainWindow(ProductionMainWindow)" in runtime_source
    assert "class ProductionMainWindow(HardenedMainWindow)" in production_source
    assert "class HardenedMainWindow(MainWindow)" in hardened_source


def test_main_window_direct_execution_routes_to_canonical_main():
    source = MAIN_SHIM.read_text(encoding="utf-8")
    assert "from src.ui.legacy_window import" in source
    assert "from src.main import main as production_main" in source
    assert "raise SystemExit(main())" in source
    assert "window = MainWindow()" not in source


def test_smoke_gui_bootstraps_repo_root_before_app_import():
    source = SMOKE_GUI.read_text(encoding="utf-8")
    root_bootstrap = "ROOT = Path(__file__).resolve().parents[1]"
    path_insert = "sys.path.insert(0, str(ROOT))"
    app_import = "from src.ui.runtime_window import RuntimeMainWindow"

    assert root_bootstrap in source
    assert path_insert in source
    assert app_import in source
    assert source.index(path_insert) < source.index(app_import)


def test_failed_start_guard_is_generation_based_not_timer_based():
    source = PRODUCTION.read_text(encoding="utf-8")
    assert "self.process.started.connect" in source
    assert "self._failed_start_pending = True" in source
    assert "self._failed_start_pending = False" in source
    assert "_clear_failed_start_guard" not in source


def test_legacy_parser_is_only_imported_by_hardened_parser_facade():
    direct_import = "src.logic.legacy_parser"
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if direct_import in source and path != PARSER_FACADE:
            offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []
    facade_source = PARSER_FACADE.read_text(encoding="utf-8")
    assert "from src.logic.legacy_parser import *" in facade_source

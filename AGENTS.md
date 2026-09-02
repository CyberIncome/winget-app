# Repository Guidelines

## Project Structure & Module Organization
- `src/main.py` is the canonical GUI entry point and constructs `StartupOptimizedMainWindow`.
- The canonical GUI inheritance stack is intentionally layered: `StartupOptimizedMainWindow -> VersionIntegrityMainWindow -> VersionAwareMainWindow -> WorkbenchMainWindow -> ProductMainWindow -> ExperienceMainWindow -> RuntimeMainWindow -> ProductionMainWindow -> HardenedMainWindow -> historical presentation`.
- `src/ui/startup_optimized_window.py` owns the final startup schedule: authoritative WinGet and local inventory scans may run concurrently, readiness waits for both base scans, and optional Detective/GitHub/app-release enrichment is deferred until after that base boundary. Inventory refresh remains guarded while Detective owns an inventory snapshot.
- `src/ui/version_integrity_window.py` owns final scan-target identity and asynchronous version-reconciliation lifecycle guards.
- `src/ui/version_aware_window.py` owns Windows-vs-WinGet version provenance, exact target-version execution, version-review UX, and read-only double-click inspection.
- `src/ui/workbench_window.py` owns WinGet restore-list export, exact package inspection, and update-batch cancellation.
- `src/ui/product_window.py` owns bounded activity history, snapshot export, periodic read-only update scans, and version-specific skipped updates.
- `src/ui/experience_window.py` owns app-release awareness, confirmation policy, About/diagnostics surfaces, ignored-update settings, and batch-result summaries.
- `src/ui/runtime_window.py` remains the final release-facing QProcess/shutdown exception boundary beneath those product layers.
- `src/ui/production_window.py` contains package-provenance, process-protocol, and Qt compatibility guards.
- `src/ui/hardened_window.py` owns managed process jobs, watchdog semantics, deterministic shutdown, and the accepted hardened controller behavior beneath the optimized startup layer.
- `src/ui/selection_polish.py` is the final checkbox/row-selection interaction pass. Checked rows are action state; row highlighting is inspection state. Do not reconnect the historical bidirectional selection-to-checkbox mirror.
- `src/ui/layout_polish.py` and `src/ui/context_polish.py` normalize the fully constructed layered GUI after feature construction without owning package execution logic.
- `src/ui/main_window.py` is an import-compatible model/presentation shim; the historical implementation is preserved in `src/ui/legacy_window.py`.
- `src/logic/inventory_scan.py` provides the managed GUI inventory fast path and reuses one `WScript.Shell` COM automation object for a whole shortcut scan while preserving the inventory surface.
- `src/logic/` contains command construction, strict Winget parsing, version provenance, bounded subprocess capture, Windows Job Object containment, configuration, HTTPS policy, worker targets, history, release awareness, and legacy inventory/version heuristics.
- `tests/` contains pytest suites (`test_*.py`) covering UI and logic, including native Windows process-tree containment.
- `scripts/verify_windows.py` is the release-relevant local Windows verification gate; `scripts/smoke_gui.py` exercises canonical polished product Qt construction/teardown without running scans.
- `scripts/build_windows.py` builds the public portable GUI/CLI assets; `scripts/build_release.py` builds the complete installer/release bundle.
- `conductor/` stores historical product specs, plans, and style guides.
- `docs/reliability-hardening/` is historical evidence for the accepted hardening baseline. Do not rewrite past PASS claims to imply later product-evolution work was part of that acceptance.

## Build, Test, & Development Commands
- `python -m venv .venv` creates a virtual environment.
- `pip install -r requirements-dev.txt` installs runtime plus development/test/build dependencies.
- `python -m src.main` runs the canonical GUI from the repo root.
- `python -m src.cli --help` shows CLI commands.
- `pytest` runs the full test suite.
- `pytest tests/test_upgrade_parser.py` runs the strict parser tests.
- On Windows, `python scripts/verify_windows.py` runs the local deterministic acceptance gate without GitHub Actions.
- On Windows, `python scripts/verify_windows.py --live-winget` additionally performs a read-only real Winget scan.
- On Windows, `python scripts/verify_windows.py --build` additionally builds and launch-smokes the portable GUI/CLI assets.
- On Windows, `python scripts/verify_windows.py --live-winget --installer` is the strongest release gate: it builds the complete bundle and exercises temporary install/launch/uninstall.
- `python scripts/build_windows.py --clean-output` builds `WingetUniversalDashboard-Portable-x64.exe` and `WingetUniversalDashboard-CLI-x64.exe`.
- `python scripts/build_release.py` builds the setup executable, portable assets, `BUILD_INFO.json`, and `SHA256SUMS.txt` from a clean source-bound commit.

## Coding Style & Naming Conventions
Follow `conductor/code_styleguides/*.md` (Google Python Style Guide summary):
- 4-space indentation, max line length 80 where practical.
- `snake_case` for functions/variables, `PascalCase` for classes, `ALL_CAPS` for constants.
- Use docstrings for public modules/classes/functions; prefer explicit, readable control flow.
- Avoid mutable default arguments; use `if x is None:` checks.
- Group imports: stdlib, third-party, local.
- Prefer thin additive product layers over modifying the large historical presentation class when a feature can be isolated above an already accepted safety boundary.

## Testing Guidelines
- Frameworks: `pytest` + `pytest-qt` (`qtbot` fixture).
- Test files are named `test_*.py`; keep UI tests deterministic (no modal dialogs or uncontrolled startup scans).
- Add regression tests for every reliability/correctness bug fixed.
- Pure-Python logic should be testable without Qt/Windows where possible.
- Native PySide6/pywin32/COM/WinGet behavior must pass `scripts/verify_windows.py` on Windows before a new branch is described as Windows-verified.
- Packaged-release acceptance should pass `python scripts/verify_windows.py --live-winget --installer`.
- Managed read-only WinGet subprocesses that run inside cancellable spawned workers must require Windows process-tree containment; cancellation must not strand a descendant `winget.exe`.
- Startup optimization must not weaken package authority: base readiness still requires the authoritative WinGet scan and local inventory scan to settle, while optional enrichment may continue afterward.

## Commit & Pull Request Guidelines
- Commit messages are short and imperative; Conventional Commit style is preferred.
- Reliability/product work should remain logically isolated and evidence-backed.
- PRs should describe the change, list verification performed, identify Windows-only gates still pending, and distinguish inherited baseline evidence from evidence collected for the PR head.
- Include screenshots or a short GIF when visual UI/QSS behavior changes materially.

## Configuration & Security Notes
- This is a Windows-focused app (uses `pywin32` and native Windows APIs); avoid platform-specific assumptions without guards.
- Keep secrets and machine-specific paths out of the repo; GitHub PATs belong in the OS credential store, not JSON config.
- Network version checks must use the bounded HTTPS helper and must not forward secrets across origins.
- Only rows explicitly proven by the current Winget scan may trigger Winget package updates; detective-only findings are informational.
- GUI package-update identity is **match field + package + source + exact target version from the current scan**. Do not silently fall back to a newer/latest version if the scan target is missing, truncated, ambiguous, or changed.
- Windows `DisplayVersion` and WinGet manifest `PackageVersion` are not assumed to share one numbering scheme. Preserve provenance and review warnings rather than inventing downgrade/upgrade semantics.
- Managed read-only/background WinGet commands use kill-on-close Windows Job Object containment when cancellation/shutdown ownership requires the entire process tree to terminate.
- The current HTTPS policy does not provide a DNS/IP-level private-network denylist; do not describe detective URL handling as full SSRF isolation.

# Repository Guidelines

## Project Structure & Module Organization
- `src/main.py` is the canonical GUI entry point and constructs `ProductionMainWindow`.
- `src/ui/production_window.py` contains final package-provenance and Qt compatibility guards.
- `src/ui/hardened_window.py` owns staged startup, process/job lifecycle, watchdogs, and shutdown behavior.
- `src/ui/main_window.py` is an import-compatible shim; the historical presentation/model implementation is preserved in `src/ui/legacy_window.py`.
- `src/logic/` contains command construction, strict Winget parsing, configuration, HTTPS policy, worker targets, and legacy inventory/version heuristics.
- `tests/` contains pytest suites (`test_*.py`) covering UI and logic.
- `scripts/verify_windows.py` is the release-relevant local Windows verification gate; `scripts/smoke_gui.py` exercises production Qt construction/teardown without running scans.
- `conductor/` stores historical product specs, plans, and style guides.
- `docs/reliability-hardening/` contains the current hardening plan and verification evidence.

## Build, Test, & Development Commands
- `python -m venv .venv` creates a virtual environment.
- `pip install -r requirements-dev.txt` installs runtime plus development/test dependencies.
- `python -m src.main` runs the hardened GUI from the repo root.
- `python -m src.cli --help` shows CLI commands.
- `pytest` runs the full test suite.
- `pytest tests/test_upgrade_parser.py` runs the strict parser tests.
- On Windows, `python scripts/verify_windows.py` runs the full local acceptance gate without GitHub Actions.
- On Windows, `python scripts/verify_windows.py --live-winget` additionally performs a read-only real Winget scan.

## Coding Style & Naming Conventions
Follow `conductor/code_styleguides/*.md` (Google Python Style Guide summary):
- 4-space indentation, max line length 80 where practical.
- `snake_case` for functions/variables, `PascalCase` for classes, `ALL_CAPS` for constants.
- Use docstrings for public modules/classes/functions; prefer explicit, readable control flow.
- Avoid mutable default arguments; use `if x is None:` checks.
- Group imports: stdlib, third-party, local.

## Testing Guidelines
- Frameworks: `pytest` + `pytest-qt` (`qtbot` fixture).
- Test files are named `test_*.py`; keep UI tests deterministic (no modal dialogs or startup scans).
- Add regression tests for every reliability/correctness bug fixed.
- Pure-Python logic should be testable without Qt/Windows where possible.
- Native PySide6/pywin32/COM/WinGet behavior must pass `scripts/verify_windows.py` on Windows before a release is described as Windows-verified.

## Commit & Pull Request Guidelines
- Commit messages are short and imperative; Conventional Commit style is preferred.
- Reliability work should remain logically isolated and evidence-backed.
- PRs should describe the change, list verification performed, and identify any Windows-only gates still pending.
- Include screenshots or a short GIF only when visual UI/QSS behavior changes.

## Configuration & Security Notes
- This is a Windows-focused app (uses `pywin32`); avoid platform-specific assumptions without guards.
- Keep secrets and machine-specific paths out of the repo; GitHub PATs belong in the OS credential store, not JSON config.
- Network version checks must use the bounded HTTPS helper and must not forward secrets across origins.
- Only rows explicitly proven by the current Winget scan may trigger Winget package updates; detective-only findings are informational.

# Repository Guidelines

## Project Structure & Module Organization
- `src/main.py` is the GUI entry point.
- `src/ui/` holds PySide6 UI code plus `styles.qss` for theming.
- `src/logic/` contains non-UI logic (parsing, execution helpers).
- `tests/` contains pytest suites (`test_*.py`) covering UI and logic.
- `conductor/` stores product specs, plans, and style guides used for internal planning.
- `requirements.txt` defines runtime and test dependencies.

## Build, Test, and Development Commands
- `python -m venv .venv` (optional) create a virtual environment.
- `pip install -r requirements.txt` install dependencies.
- `python -m src.main` run the app from the repo root.
- `pytest` run the full test suite.
- `pytest tests/test_parser.py -k parse` run a focused test selection.

## Coding Style & Naming Conventions
Follow `conductor/code_styleguides/*.md` (Google Python Style Guide summary):
- 4-space indentation, max line length 80.
- `snake_case` for functions/variables, `PascalCase` for classes, `ALL_CAPS` for constants.
- Use docstrings for public modules/classes/functions; prefer f-strings.
- Avoid mutable default arguments; use `if x is None:` checks.
- Group imports: stdlib, third-party, local.

## Testing Guidelines
- Frameworks: `pytest` + `pytest-qt` (`qtbot` fixture).
- Test files named `test_*.py`; keep UI tests deterministic (no modal dialogs or long-running timers).
- No explicit coverage target; add tests for new logic and UI behaviors you change.

## Commit & Pull Request Guidelines
- Commit messages are short and imperative; Conventional Commit style is used in places (e.g., `feat(inventory): ...`).
- PRs should describe the change, list tests run, and link relevant issues/tracks when applicable.
- Include screenshots or a short GIF for UI/QSS changes.

## Configuration & Security Notes
- This is a Windows-focused app (uses `pywin32`); avoid platform-specific assumptions without checks.
- Keep secrets and machine-specific paths out of the repo; use environment variables or user config files instead.

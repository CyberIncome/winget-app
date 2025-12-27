# Track Specification - Build the Core Update Dashboard

## Overview
This track focuses on building the foundational components of WingetGui: the environment setup, the winget output parser, and the primary dashboard GUI.

## Technical Requirements

### 1. Environment & Project Structure
- **Language:** Python 3.11+
- **GUI Framework:** PySide6
- **Dependencies:** `PySide6`
- **Structure:**
  - `src/main.py`: Entry point.
  - `src/logic/parser.py`: Logic for parsing `winget` output.
  - `src/logic/executor.py`: Logic for running `winget` commands.
  - `src/ui/main_window.py`: Main dashboard UI.
  - `src/ui/styles.qss`: Theme definitions.
  - `tests/`: TDD unit tests.

### 2. Winget Parser Logic
- Command: `winget upgrade --include-unknown`
- Goal: Capture stdout and convert the tabular data into a list of Python dictionaries.
- Required Fields: `Name`, `Id`, `Version`, `Available`, `Source`.
- Edge Case: Handle situations where no updates are available.

### 3. Dashboard UI
- **Table:** Sortable table with checkboxes in the first column.
- **Console:** A read-only `QPlainTextEdit` at the bottom to pipe `winget` output.
- **Buttons:** "Refresh", "Update Selected", "Update All".
- **Theme:** Forced Dark Mode via QSS.

### 4. CLI Execution
- Must use `QProcess` or a similar asynchronous mechanism to prevent GUI freezing.
- Capture real-time output for the integrated console.

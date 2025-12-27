# Technology Stack - WingetGui

## Core Development
- **Language:** Python 3.11+
- **GUI Framework:** PySide6 (Qt for Python)
- **Architecture:** Procedural/Object-Oriented with a dedicated `WingetProcess` handler for non-blocking CLI calls.

## Styling & Theme
- **Theme Engine:** Qt Style Sheets (QSS) for custom "Cyber/Tech" styling.
- **Color Palette:** Pure Black (#000000), Neon Blue (#00F2FF), Electric Green (#39FF14).
- **Fonts:** Cascadia Code / Consolas (Monospaced).

## CLI Integration
- **Execution:** Python `subprocess` module for running `winget` commands.
- **Parsing:** Custom regex-based parser to translate winget's tabular output into Python dictionaries.
- **Handling:** `QThread` or `QProcess` to ensure the GUI remains responsive while winget is running.

## Distribution
- **Packaging:** PyInstaller for creating a standalone Windows executable.

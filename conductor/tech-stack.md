# Technology Stack - WingetGui

## Core Development
- **Language:** Python 3.11+
- **GUI Framework:** PySide6 (Qt for Python)
- **Architecture:** Procedural/Object-Oriented with a dedicated `WingetProcess` handler for non-blocking CLI calls.

## Styling & Theme
- **Theme Engine:** Qt Style Sheets (QSS) for custom "Modern Glassmorphism" styling.
- **Color Palette:** Deep Slate (#1A1B26), Soft Electric Blue (#7AA2F7), Emerald Green (#9ECE6A).
- **Fonts:** Segoe UI / Inter (UI), Cascadia Code / Consolas (Monospaced Logs).

## CLI Integration
- **Execution:** Python `subprocess` module for running `winget` commands.
- **Parsing:** Custom regex-based parser to translate winget's tabular output into Python dictionaries.
- **Handling:** `QThread` or `QProcess` to ensure the GUI remains responsive while winget is running.

## Distribution
- **Packaging:** PyInstaller for creating a standalone Windows executable.

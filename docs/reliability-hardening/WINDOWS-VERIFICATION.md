# Local Windows Verification Gate

The application is Windows-specific, and the most important reliability paths
involve PySide6, Win32 APIs, COM, multiprocessing `spawn`, and the real Winget
executable. These behaviors cannot be proven by Linux-only static analysis.

This repository therefore ships a local Windows acceptance gate instead of
requiring GitHub Actions:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python scripts\verify_windows.py
```

The deterministic default gate runs:

1. Python bytecode compilation for `src`, `tests`, and `scripts`.
2. Ruff correctness checks (`E9`, `F63`, `F7`, `F82`).
3. The complete pytest suite, including pytest-qt UI tests.
4. A CLI import/command smoke test.

For an additional read-only check against the machine's real App Installer /
Winget stack:

```powershell
python scripts\verify_windows.py --live-winget
```

That adds:

- `winget --version`
- `python -m src.cli --json-output check`

The live scan reads installed-package/registry state but does **not** install or
upgrade anything.

## Release evidence

When validating a release candidate, keep the terminal output with the commit
SHA being tested. The script prints the installed versions of PySide6,
pywin32, requests, click, keyring, pytest, pytest-qt, and Ruff so a successful
Windows run establishes the actual dependency baseline that earned release
acceptance.

A branch should not be described as natively Windows-verified unless this gate
has been run successfully on Windows. Static/offline checks from another OS are
supporting evidence, not a substitute for this gate.

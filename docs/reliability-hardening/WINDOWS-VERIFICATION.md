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
3. A named native Windows lifecycle suite that uses synthetic Python children
   only. It exercises real multiprocessing `spawn`, managed-job success,
   cancellation, timeout, abrupt child exit, QProcess `FailedToStart`
   recovery, QProcess crash/no-retry behavior, watchdog kill/no-retry behavior,
   and closing `ProductionMainWindow` while an owned spawned child is active.
   It also exercises the hardened remote-version detector with fake network
   responses; it does not install, remove, or update packages.
4. The complete pytest suite, including pytest-qt production/lifecycle tests.
5. A CLI import/command smoke test.
6. `scripts/smoke_gui.py`, which creates, shows, and cleanly closes the real
   `ProductionMainWindow` before startup scans begin. This exercises target-OS
   Qt/Win32 construction and teardown without invoking Winget or modifying the
   machine.

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

## Manual crash-boundary exercise

After the deterministic gate passes, the highest-value manual checks are:

1. Launch `python -m src.main` and let startup complete.
2. Refresh Updates and Inventory several times; confirm duplicate clicks do not
   create duplicate background jobs and the UI always returns to idle.
3. Start an Inventory scan and immediately close the window; confirm the app
   exits without a lingering Python child process.
4. Start a Winget update on a package you intentionally choose, then close the
   app while the child is active; confirm shutdown is bounded and the next app
   launch is clean.
5. Temporarily disable/rename the Winget App Execution Alias, launch the app,
   and confirm one FailedToStart message is shown and an update batch is
   aborted rather than repeatedly retrying every queued package. Restore the
   alias afterward.
6. Review the latest `winget_gui.log` / `winget_crash.log`; a normal close must
   contain the same session ID from `SESSION START` through `SESSION CLEAN EXIT`.

## Release evidence

When validating a release candidate, keep the terminal output with the commit
SHA being tested. The script prints the installed versions of PySide6,
pywin32, requests, click, keyring, pytest, pytest-qt, and Ruff so a successful
Windows run establishes the actual dependency baseline that earned release
acceptance.

A branch should not be described as natively Windows-verified unless this gate
has been run successfully on Windows. Static/offline checks from another OS are
supporting evidence, not a substitute for this gate.

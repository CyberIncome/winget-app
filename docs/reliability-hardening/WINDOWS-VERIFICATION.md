# Local Windows Verification Gate

The application is Windows-specific, and the most important remaining acceptance boundaries involve PySide6, Win32 APIs, COM, multiprocessing `spawn`, the OS credential store, PyInstaller, and the real Winget executable. Those behaviors cannot be honestly proven by the Linux audit host.

This repository therefore ships a local Windows acceptance gate instead of requiring GitHub Actions.

## Deterministic source/runtime gate

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python scripts\verify_windows.py
```

The default gate runs:

1. Python compilation for `src`, `tests`, and `scripts`.
2. Ruff correctness checks (`E9`, `F63`, `F7`, `F82`).
3. Native Windows lifecycle tests using synthetic Python children. These exercise real multiprocessing `spawn`, managed-job success/cancel/timeout/abrupt exit, QProcess `FailedToStart`, crash/no-retry behavior, watchdog kill/no-retry behavior, hostile QProcess teardown failures, synchronous refresh/batch/watchdog exception containment, and closing the canonical `RuntimeMainWindow` while an owned spawned child is active.
4. The complete pytest/pytest-qt suite.
5. CLI import/command smoke.
6. `scripts/smoke_gui.py`, which creates, shows, and cleanly closes `RuntimeMainWindow` before startup scans begin.

The default gate does not install, remove, or upgrade packages.

## Read-only real Winget gate

```powershell
python scripts\verify_windows.py --live-winget
```

This adds:

- `winget --version`
- `python -m src.cli --json-output check`

The live scan reads local package/registry state but does not perform an upgrade.

## Packaged-release gate

```powershell
python scripts\verify_windows.py --build
```

This additionally:

- runs `scripts/build_windows.py --clean-output`;
- builds `dist\WingetUniversalDashboard.exe` and `dist\WingetUniversalDashboardCLI.exe` with PyInstaller;
- runs the packaged CLI with `--help`;
- launches the packaged GUI with the private `WUD_PACKAGED_SMOKE=1` mode, which constructs and cleanly closes the canonical runtime window before the normal startup scan begins.

For a release candidate, run both optional gates together:

```powershell
python scripts\verify_windows.py --live-winget --build
```

## Manual crash-boundary exercise

After the deterministic gate passes, perform these high-value checks:

1. Launch `python -m src.main` and let startup complete.
2. Refresh Updates and Inventory several times; confirm duplicate clicks do not create overlapping foreground work and the UI returns to idle.
3. Start an Inventory scan and immediately close the window; confirm the app exits without a lingering Python child.
4. Start a Winget update on a package you intentionally choose, then close the app while the child is active; confirm shutdown is bounded and the next launch is clean.
5. Temporarily disable/rename the Winget App Execution Alias, launch the app, and confirm one FailedToStart message is shown and an update batch is aborted instead of retrying the unavailable executable for each queued package. Restore the alias afterward.
6. Exercise at least one normal installer failure if practical and confirm only a normal non-zero exit gets the one retry without `--silent`; crashes/timeouts must not.
7. Review the latest `winget_gui.log` / `winget_crash.log`; a normal close must contain the same session ID from `SESSION START` through `SESSION CLEAN EXIT`.
8. If packaging a release, repeat the open/close and one read-only scan using the built GUI executable.

## Release evidence

Keep the terminal output together with the exact commit SHA being tested. `scripts/verify_windows.py` prints Python and installed versions of PySide6, pywin32, requests, click, keyring, pytest, pytest-qt, Ruff, and PyInstaller so a successful Windows run records the dependency baseline that earned acceptance.

A branch must not be described as natively Windows-verified or release-accepted until this gate has passed on Windows. Static/offline checks from another OS are supporting evidence, not a substitute.

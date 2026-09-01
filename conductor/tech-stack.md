# Technology Stack - WingetGui

## Core Development
- **Language:** Python 3.11+
- **GUI Framework:** PySide6 (Qt for Python)
- **Production GUI Entry:** `src.main` -> `ProductionMainWindow`
- **Presentation Base:** Historical widgets/models remain in `src/ui/legacy_window.py`; `src/ui/main_window.py` is a compatibility shim and routes direct execution through the production entry point.

## Runtime Concurrency & Process Model
- **Winget execution:** One long-lived Qt `QProcess` owned by the GUI for real-time stdout/stderr and update sequencing.
- **Inventory / parsing / detective / API work:** Isolated `multiprocessing` workers using the Windows-safe `spawn` context, owned and polled by `ManagedProcessJob` from the Qt event loop.
- **Lifecycle policy:** Background jobs have explicit timeout, cancellation, join/terminate/kill cleanup, and queue cleanup. Production orchestration does not use fire-and-forget daemon threads.
- **Startup:** Heavy work is staged (`Winget refresh -> inventory -> detective -> API`) instead of launched concurrently.

## Winget Integration
- **Command construction:** `src/logic/executor.py` builds argument arrays; no shell interpolation is used.
- **Package targeting:** Single-package updates use exact ID/name matching and retain the Winget source when available.
- **Interactivity:** Programmatic scans/updates accept required agreements and disable Winget-side interactivity; installer `--silent` can be retried without silent only after an ordinary non-zero exit, not a crash or timeout.
- **Parsing:** `winget upgrade` has no stable JSON output, so `src/logic/upgrade_parser.py` treats the formatted table as an external protocol and fails closed on malformed/truncated rows.

## Inventory & Remote Version Detection
- **Windows inventory:** Registry, shortcuts/COM, executable metadata, and bounded filesystem heuristics in the historical parser module.
- **Remote detective:** HTTPS-only bounded retrieval through `src/logic/http_safety.py`; detector results are informational unless a current Winget scan independently proves the package upgradeable.
- **Credentials:** GitHub PAT is stored through the OS keyring/Credential Manager rather than plaintext config.

## Styling & Theme
- **Theme Engine:** Qt Style Sheets (QSS) for the Modern Glassmorphism styling.
- **Color Palette:** Deep Slate, Soft Electric Blue, Emerald Green.
- **Fonts:** Segoe UI / Inter (UI), Cascadia Code / Consolas (monospaced logs).

## Verification
- **Tests:** pytest + pytest-qt.
- **Static correctness:** Ruff correctness rules plus Python compilation/AST checks.
- **Target-OS gate:** `scripts/verify_windows.py` runs locally on Windows and includes a production GUI create/close smoke test; GitHub Actions is not required for this hardening branch.

## Distribution
- **Intended packaging:** PyInstaller for a standalone Windows executable.
- **Current repository state:** No PyInstaller `.spec` file is presently tracked. `.spec` files are intentionally not ignored so a future reproducible build recipe can be committed and reviewed.

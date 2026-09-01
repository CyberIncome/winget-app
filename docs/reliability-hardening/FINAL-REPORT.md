# Winget Universal Dashboard — Reliability Hardening Final Audit Report

Date: 2026-09-01
Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

## Executive summary

The repository was audited from its entry points through GUI orchestration, Winget command construction and parsing, Windows inventory/version discovery, background execution, configuration persistence, remote-version HTTP behavior, tests, launchers, repository hygiene, and verification tooling.

The original application had several plausible crash/hang paths and a number of correctness paths that could make a failure look like a successful empty scan or could execute an update with weaker package provenance than the UI implied. The hardening branch restructures those areas without replacing the historical presentation layer.

At the end of the implementation/static audit:

- no known implementation/static audit failure remains open;
- the production GUI no longer relies on unowned fire-and-forget daemon threads for long-running inventory, parse, detective, or API work;
- startup is staged and shutdown owns/cancels spawned work;
- Winget process failures are separated into start failure, crash, timeout, normal failure, and success;
- malformed or partial Winget upgrade output fails closed;
- package source provenance is preserved for exact update targeting;
- registry uninstall IDs are no longer treated as Winget IDs;
- detective-only version findings are informational rather than executable authority;
- configuration and PAT persistence are substantially safer;
- HTTP redirects are bounded and cross-origin credential forwarding is constrained;
- tracked generated caches and misleading historical audit output are removed;
- a reproducible local Windows acceptance gate is included because GitHub Actions minutes are unavailable.

The branch is **not yet release-accepted**. Native Windows behavior involving PySide6, `QProcess`, COM, pywin32, multiprocessing `spawn`, App Installer, the credential store, and the real Winget executable still requires the supplied Windows acceptance procedure.

## Architecture after hardening

### Canonical GUI path

`launcher.py` -> `src.main.main()` -> `ProductionMainWindow`

`ProductionMainWindow` extends `HardenedMainWindow`, which extends the historical `MainWindow` implementation. The historical presentation/model code is preserved in `src/ui/legacy_window.py`. `src/ui/main_window.py` is a compatibility export shim and its direct-execution path routes back through `src.main`, preventing an alternate launch from silently bypassing the production safety layer.

### Background work

The production GUI uses `ManagedProcessJob` for expensive/background operations:

- registry + total inventory scan;
- strict Winget-output parsing and registry enrichment;
- remote-version detective scan;
- GitHub rate-limit status.

Worker targets serialize one success/failure envelope through a multiprocessing queue. The Qt-side owner provides bounded timeout, cancellation, terminate/join/kill escalation, queue cleanup, and lifecycle logging.

The main Winget update/scan process remains a Qt `QProcess`, because it needs live stdout/stderr/progress integration. Its lifetime is explicitly watched and terminated during shutdown.

## Highest-impact defects found and repaired

### 1. Unowned background thread lifecycle — high reliability impact

The historical window launched daemon Python threads for inventory, detective/API work, and parsing. Those threads could outlive closing Qt objects and had no deterministic cancellation or ownership.

Production overrides route the long-running work through managed spawned processes. A static regression test now discovers every legacy method containing a `threading.Thread` launch and asserts that the production inheritance chain overrides it.

### 2. Overlapping startup workload — high reliability/performance impact

The old startup scheduled update scan, inventory scan, and API work independently within a short interval. Inventory could also trigger detective work immediately, producing simultaneous registry/COM/network/Qt activity.

Startup now advances through explicit stages: refresh -> parse -> inventory -> detective -> API.

### 3. QProcess failure-state conflation — high reliability/correctness impact

Failed-to-start, crash, timeout, normal installer failure, and success previously shared too much completion behavior. In particular, a crash could enter retry logic intended only for a normal non-silent installer failure.

The hardened controller tracks crash and timeout state separately. Only a normal non-zero package update may retry once without `--silent`. A missing Winget executable aborts the remaining batch rather than attempting the same impossible start repeatedly.

### 4. Output-idle watchdog false positives — high reliability impact

The old watchdog killed a process because it had produced no output for a fixed interval. A legitimate installer can remain silent while still making progress.

The watchdog now uses total elapsed time as the hard termination condition. Output silence produces a diagnostic warning only.

### 5. Winget table parsing failed open — high correctness impact

The historical parser could treat malformed output as zero updates and could accept partial tables while silently dropping malformed/truncated rows.

The strict parser validates required columns, ordering, separator structure, row boundaries, and every package row. Any malformed data row fails the entire parse. An empty recognized table also fails unless Winget emitted a recognized no-update marker.

### 6. Package-source provenance loss — high update-safety impact

A package ID is not necessarily globally unique across configured sources. The update model originally did not retain source identity through checkbox selection, deduplication, command construction, or row removal.

Source is now displayed and retained in the executable package reference. Duplicate IDs from separate sources maintain independent checkbox state and separate update refs. Exact update commands include `--source` when the scan supplied it. Current Microsoft WinGet behavior explicitly supports source restriction for this kind of disambiguation.

### 7. Registry uninstall IDs treated as Winget provenance — high update-safety impact

Inventory `Id` values come from Windows uninstall registry subkeys. They are local inventory identifiers, not proof of a Winget package identity. The final adversarial pass found that an accidental registry-ID collision with a different Winget package could theoretically select the wrong update row.

Inventory-triggered updates now ignore inventory IDs completely. They require exactly one case-insensitive exact name match among current authoritative Winget upgrade rows; zero or multiple matches fail closed and no command is run.

### 8. Detective results could alter executable update state — medium/high correctness impact

Remote-version detective results could overwrite a Winget-provided `Available` value or add a row that looked like a normal update target.

Winget results remain authoritative. Detective-only rows are tagged as detective information and are excluded from Update All/Update Selected execution unless a current Winget upgrade row independently proves upgradeability.

### 9. Selector validation bug found during verification — medium safety impact

The hardening work initially used regex/end trimming in a way that could allow a newline-adjacent selector/source value through validation. The executable adversarial gate caught this defect in the new code before completion was accepted.

Validation now rejects CR, LF, and NUL explicitly and uses full-string matching for package IDs. Regression tests cover leading/trailing newline and embedded control-character cases.

### 10. HTTP redirect credential propagation — medium security impact

The hardened transport initially removed explicit secret headers on cross-origin redirects but still retained caller-provided Requests `auth=` and `cookies=` keyword arguments across manual redirect hops.

Cross-origin redirects now clear Authorization/Proxy-Authorization/Cookie headers as well as explicit `auth=` and `cookies=` kwargs. HTTPS-only validation, redirect count limits, response-size caps, and credential-bearing URL rejection remain in force.

### 11. Config/PAT persistence — medium reliability/security impact

Configuration now uses deep-copied defaults and values, atomic temp-file + fsync + replace writes, corrupt-file quarantine, and safe legacy PAT migration to the OS credential store. PAT edits are debounced rather than synchronously persisted on every keystroke, and a pending edit is flushed when the production window closes.

### 12. CLI and GUI contract drift — medium correctness impact

CLI `check`/`status` had independently constructed Winget scan commands and `status` repeated registry work. CLI scans now use the same hardened noninteractive scan command as the GUI, expose source information, reuse registry data in `status`, and terminate/kill a live update child on Ctrl+C.

### 13. Alternate legacy GUI entry point — medium reliability impact

Executing the historical `main_window.py` directly could bypass the production controller. The old implementation is preserved as `legacy_window.py`; `main_window.py` now exports compatibility symbols and delegates direct execution to the canonical production entry point.

### 14. Repository audit/cache contamination — quality/diagnostic impact

Tracked `.pyc`/`__pycache__` artifacts were removed. Earlier generated audit reports had accidentally inspected a local virtual environment and some contained only encoding-error output. Those reports were removed rather than preserved as misleading evidence.

## Verification performed

### Executed in the current environment

Because the current execution host is Linux and lacks PySide6/Windows APIs, verification was split rather than pretending cross-platform execution proves Windows behavior.

Executable pure-Python checks were rerun from exact branch source fetched through the connected GitHub repository interface. They covered:

- package ID/name/source validation and exact source-aware Winget command construction;
- strict table parsing and malformed/partial table rejection;
- command-runner success, non-zero exit, timeout, start failure, and wide-column environment behavior;
- config deep-copy, atomic save, quarantine, and PAT migration behavior;
- HTTPS URL validation, redirect safety, body caps, header-secret stripping, and auth/cookie kwarg stripping.

The final tree was also inspected for generated caches and workflows, and the large-file writes made during the second audit were compared against their immediate parents to ensure unrelated code was not accidentally replaced.

### Regression tests committed for Windows/Qt

The branch includes regression coverage for:

- production GUI source-aware update rows;
- duplicate IDs from multiple sources;
- independent source-aware checkbox state;
- registry-ID collision prevention;
- ambiguous inventory names failing closed;
- detective-only informational behavior;
- preservation of authoritative Winget versions;
- FailedToStart batch abort;
- CrashExit no-retry behavior;
- pending PAT flush at close;
- canonical hardened entrypoint;
- legacy daemon-thread launch methods being overridden;
- managed spawned-process cleanup;
- CLI scan-command parity;
- production Qt create/show/clean-close smoke behavior.

## Verification failures that changed the implementation

This audit deliberately records failed verification rather than reporting only green results.

The most important example was the selector/source control-character gate. It failed after the first hardening implementation, demonstrating that the validator could accept a newline-adjacent value. The implementation and tests were changed, and the executor gate was restarted from zero and passed.

The final adversarial architecture pass also found the registry-ID provenance collision and cross-origin `auth=`/`cookies=` issue after earlier phases had appeared complete. Both were added to scope, repaired, and regression-tested. These are concrete examples of the "do not accept finished blindly" process applied to this repository.

## Repository state

The branch is intentionally based on the original `master` commit listed above and has remained ahead of—not behind—the base during the hardening work. Application-source deletions were not used as a shortcut; the major apparent `main_window.py` deletion in the branch diff is the move of the exact historical implementation to `legacy_window.py` plus a small compatibility shim.

The final tree contains no tracked Python bytecode caches and no GitHub Actions workflow. Runtime and verification dependencies are separated into `requirements.txt` and `requirements-dev.txt`.

## Remaining risk / required native acceptance

No static/pure-Python implementation failure is currently open, but the following claims require the actual Windows runtime and therefore remain `WINDOWS-VERIFY`:

- PySide6 `QProcess` signal ordering around FailedToStart/CrashExit/kill;
- clean window close while spawned Windows inventory/COM work is active;
- multiprocessing `spawn` behavior in the packaged/runtime environment;
- pywin32 COM shortcut resolution and registry behavior on the target Windows version;
- OS credential-store/keyring behavior;
- App Installer/Winget executable behavior and real table formatting;
- native crash/fault logging;
- production UI interaction during real installs.

Run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python scripts\verify_windows.py --live-winget
```

Then perform the manual crash-boundary checks in `WINDOWS-VERIFICATION.md`.

## Merge/release recommendation

**Implementation/static audit:** PASS

**Native Windows acceptance:** PENDING

**Merge/release recommendation:** HOLD until the Windows gate and manual crash-boundary checks pass on the target machine. If they pass without producing a new failure, the branch is a substantially safer candidate than `master` for normal use and further packaging work.

# Reliability Hardening Verification

Status: IMPLEMENTATION/STATIC AUDIT COMPLETE — NATIVE WINDOWS ACCEPTANCE PENDING

This file is the evidence ledger for `audit/ferrox-reliability-hardening`.

## Evidence rules

- Implementation claims are not accepted merely because code changed.
- Each must-have resolves to `VERIFIED`, `FAILED`, or `WINDOWS-VERIFY`.
- `WINDOWS-VERIFY` is used only where the current environment cannot exercise a Windows/Qt/WinGet boundary honestly.
- Any `FAILED` must-have blocks merge.
- `WINDOWS-VERIFY` is not a failure, but it does block describing the branch as release-accepted until the local Windows gate passes.

## Must-have ledger

| Must-have | Status | Evidence |
| --- | --- | --- |
| No untracked production daemon threads | VERIFIED | Canonical GUI route is `src.main` -> `ProductionMainWindow`; legacy direct execution routes back through `src.main`. Production overrides every legacy method containing `threading.Thread`; `tests/test_thread_override_contract.py` encodes this invariant. |
| Owned jobs have timeout/cancellation/cleanup | VERIFIED | `ManagedProcessJob` owns spawned children, polls through Qt, has a hard timeout, and performs terminate/join/kill/close plus queue cleanup. Worker-envelope tests are committed in `tests/test_worker_jobs.py`. |
| Shutdown terminates owned children | WINDOWS-VERIFY | `HardenedMainWindow.closeEvent` cancels all managed jobs and boundedly terminates/kills active `QProcess` work; native Windows spawn/QProcess behavior must be exercised locally. |
| Startup is staged | VERIFIED | Hardened startup sequences refresh -> parse -> inventory -> detective -> API instead of overlapping every heavyweight subsystem at launch. |
| Winget outcomes are distinguished | WINDOWS-VERIFY | Production/hardened handlers separately track FailedToStart, CrashExit, hard timeout, normal non-zero exit, and success; Qt signal ordering needs native verification. |
| Crash/timeout does not trigger silent retry | WINDOWS-VERIFY | Retry predicate excludes crash/timeout; `tests/test_production_ui.py` contains explicit CrashExit coverage. |
| Watchdog hard deadline is not output-idle kill | VERIFIED | Hard timeout is based on elapsed start time; idle output only emits a warning. |
| Batch returns to idle | WINDOWS-VERIFY | All normal/error terminal paths clear operation/busy state in source; real QProcess signal sequencing remains Windows/Qt evidence. |
| Parser fails explicitly on malformed tables | VERIFIED | Pure-Python adversarial assertions passed for missing headers/separators, partial malformed rows, unexplained empty tables, and unrecognized error output. |
| Parser validates columns / optional Source | VERIFIED | Pure-Python parser assertions passed for standard output and output without the optional Source column. |
| Uncertain versions remain safe | VERIFIED | Strict enrichment preserves unknown/approximate installed versions from unsafe local filtering; dedicated parser tests are committed. |
| Package/source provenance is preserved | VERIFIED | Current Microsoft WinGet docs confirm `--source` disambiguation; executor assertions passed with source-specific commands; production selection/dedup/removal keys include source. |
| Registry IDs are not Winget provenance | VERIFIED | Final source review removed registry-ID matching entirely; `tests/test_inventory_mapping.py` contains a deliberate wrong-ID collision and requires unique exact name mapping. |
| Config defaults deep copied | VERIFIED | Pure-Python config assertions passed; nested values are copied on initialization/get. |
| Config writes atomic | VERIFIED | Pure-Python config assertions passed for temp-file + fsync + replace behavior and corrupt-file quarantine. |
| PAT writes debounced | WINDOWS-VERIFY | Production uses an 800 ms Qt debounce and flushes pending PAT state on close; keyring/Qt behavior needs Windows acceptance. |
| Redirect targets constrained | VERIFIED | HTTPS/credential URL validation, redirect limits, body caps, cross-origin secret-header stripping, and cross-origin `auth=`/`cookies=` stripping passed executable fake-transport assertions. |
| Session/lifecycle diagnostics | WINDOWS-VERIFY | Session IDs, process/job lifecycle logs, Python/thread exception hooks, and native faulthandler output are present; crash-log production requires Windows execution. |
| Clean-exit marker | WINDOWS-VERIFY | Clean-close source path logs `SESSION CLEAN EXIT`; `scripts/smoke_gui.py` is included in the Windows gate. |
| Bytecode/cache artifacts removed | VERIFIED | Final recursive Git tree inspection found no tracked `__pycache__` or `.pyc` entries; ignore rules cover future caches. |
| Dependencies split/constrained | VERIFIED | Runtime and dev requirements are separate and bounded; the constrained families were checked against current package releases during the audit. |
| No CI workflow required | VERIFIED | Final tree contains no `.github/workflows`; verification is intentionally local because CI minutes are unavailable. |

## Executed deterministic evidence in this environment

The current environment has Python/pytest/click/requests but no PySide6, pywin32 Windows runtime, real Winget, or outbound shell DNS. GitHub repository contents were therefore read through the connected repository API while executable pure-Python behaviors were rerun locally from the exact fetched branch source.

Passed during the final verification loop:

- executor selector/source construction and adversarial control-character validation;
- strict Winget table parsing, including malformed/partial/empty-table failures;
- structured command execution: successful output, explicit non-zero exit, timeout, start failure, and forced `COLUMNS=300`;
- configuration deep-copy, atomic replace, corrupt quarantine, PAT migration success, and migration-failure preservation;
- HTTPS URL validation, redirect bounding, body-size cap, secret-header stripping, and the newly added `auth=`/`cookies=` cross-origin stripping;
- branch/tree hygiene inspection;
- commit self-diffs after large-file replacement to prove unrelated content was not lost.

One verification loop intentionally failed before the final pass: selector validation accepted a newline-adjacent case because of the original regex/end-trimming semantics. That implementation was repaired, regression coverage was added, and the executor gate was restarted and passed. The failed run is preserved as evidence that completion was not accepted blindly.

## Required Windows acceptance

Run on the target Windows machine from this exact branch:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python scripts\verify_windows.py --live-winget
```

The deterministic Windows gate compiles all Python sources, runs Ruff correctness checks, executes the complete pytest/pytest-qt suite, verifies CLI import, creates/shows/cleanly closes the real production Qt window, checks the Winget executable, and performs a read-only live update scan.

The manual crash-boundary scenarios in `WINDOWS-VERIFICATION.md` should then be exercised. Until that succeeds, merge/release status remains **HOLD FOR WINDOWS ACCEPTANCE** even though no implementation/static audit failure is currently open.

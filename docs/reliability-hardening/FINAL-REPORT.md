# Winget Universal Dashboard — Reliability Hardening Final Audit Report

Date: 2026-09-01
Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

## Executive verdict

The repository-wide implementation, static, architecture, and pure-Python hardening audit is complete.

The branch is materially safer than `master` across the crash/hang paths that motivated the audit: background ownership, startup overlap, QProcess state handling, shutdown races, output memory bounds, malformed Winget output, package/source provenance, selector validation, config persistence, redirect credential handling, diagnostics, and build reproducibility.

**Implementation/static/pure-Python audit: PASS.**

**Native Windows acceptance: PENDING.**

**Packaged Windows acceptance: PENDING.**

**Merge/release recommendation: HOLD only until the supplied native Windows gate passes.**

That hold is evidence-based, not a known implementation failure. The audit host is Linux and has no PySide6/pywin32/COM/real Winget runtime, so those boundaries cannot be honestly certified here.

## Final canonical architecture

```text
launcher.py
  -> src.main.main()
     -> RuntimeMainWindow
        -> ProductionMainWindow
           -> HardenedMainWindow
              -> historical MainWindow presentation
```

The historical UI implementation is preserved in `src/ui/legacy_window.py`. `src/ui/main_window.py` is an import/model compatibility shim whose direct execution routes back through `src.main`, preventing an alternate unhardened launch path.

The historical parser/inventory implementation is preserved in `src/logic/legacy_parser.py`. `src/logic/parser.py` is the compatibility facade and hardened parse/network entry points live in dedicated modules.

## What changed and why

### 1. Background work became owned work

The original GUI used daemon threads for inventory, parsing/detective/API paths. Long-running production work now runs through `ManagedProcessJob` and spawned worker processes with one-result envelopes, timeout, cancellation, terminate/join/kill escalation, queue cleanup, and lifecycle logging.

### 2. Startup became staged

Startup now progresses refresh -> parse -> inventory -> detective -> API instead of launching heavyweight registry/COM/network/process work concurrently.

### 3. QProcess states became explicit

FailedToStart, CrashExit, watchdog timeout, normal non-zero installer failure, and success are separate states. Only a normal installer failure can retry once without `--silent`; crash/timeout cannot.

A missing Winget executable aborts the rest of a batch instead of repeatedly attempting the same unavailable process.

### 4. Final QProcess exception containment moved to the canonical runtime

The first hardening pass still left synchronous `state/start/kill/wait/terminate` wrapper/handle exceptions capable of escaping button/timer/shutdown callbacks. `RuntimeMainWindow` now owns the final QProcess boundary and contains:

- refresh-start exceptions;
- update-batch-start exceptions;
- watchdog exceptions;
- close-time `state`, `terminate`, `waitForFinished`, and `kill` failures;
- managed-job cancellation failures during close.

Hostile-QProcess regression tests intentionally raise different exception families to keep this boundary broad only where shutdown/recovery requires it.

### 5. Watchdog semantics were corrected

Output silence is diagnostic only. Hard termination uses total elapsed time, avoiding false kills of quiet installers.

### 6. Winget refresh output is an explicit bounded protocol

The GUI preserves raw stdout bytes for the authoritative parser rather than decoding arbitrary readyRead chunks independently. The authoritative buffer is capped; overflow or stdout-read failure invalidates the scan and cannot become a truncated successful result.

Live rendering is separately bounded. Canonical console history remains 2,000 blocks and a never-terminated live line is limited to 16 KiB.

### 7. CLI output capture became bounded too

Non-interactive CLI execution no longer uses unbounded `capture_output=True`. stdout/stderr are written to temporary files and at most 5 MiB per stream is decoded. Overflow is explicit non-success even when the child exits 0, so a truncated update table cannot masquerade as authoritative output.

### 8. Localized Winget parsing now fails closed

The strict parser treats rendered `winget upgrade` output as a protocol:

- requires a valid table/separator layout or known no-update marker;
- supports four columns plus optional Source;
- uses terminal display-cell widths for CJK/full-width text;
- rejects malformed/partial rows as a whole-scan failure;
- preserves Winget authority even when local version parsing is uncertain;
- rejects a calculated boundary that would split adjacent non-space characters, preventing one-cell Unicode-width disagreement from shifting a package ID.

The final parser safety change initially broke a legitimate German truncated-ID fixture. Fresh current-blob testing caught that regression (14 pass / 1 fail). The invariant was narrowed correctly and the exact parser suite then passed 15/15.

### 9. Package targeting is provenance-aware

Source identity is retained in the production model, checkbox identity, package refs, deduplication, command construction, and row removal. Exact updates include `--source` when the scan supplies it.

Duplicate package IDs from different sources remain independently selectable.

### 10. Registry inventory cannot impersonate Winget identity

Windows uninstall registry IDs are local inventory identifiers, not Winget package IDs. Inventory-triggered updates no longer match on those IDs. They require one unique exact name match among current authoritative Winget upgrade rows; ambiguity fails closed.

### 11. Detective findings are informational

Remote-version detective results cannot independently authorize Winget execution and cannot overwrite the authoritative Winget `Available` value.

### 12. Selector/argument validation was tightened repeatedly

Package IDs reject:

- display truncation/trailing-dot forms;
- leading-dash option-like forms;
- whitespace/injection-like grammar;
- every ASCII control character plus DEL.

Package names and source names reject control-bearing and option-like values. Commands are always argument arrays, never shell strings.

An earlier hardening version accepted a newline-adjacent case; the executable gate caught it and the validator was repaired before acceptance.

### 13. Config/PAT persistence became interruption-safe

Config state uses deep copies, atomic temp-file + fsync + replace writes, corrupt-file quarantine, and guarded legacy PAT migration. The plaintext legacy secret is not removed until secure-store migration succeeds.

PAT editing is debounced and pending state is flushed by the canonical runtime close path.

### 14. Remote HTTP behavior is bounded

Remote version requests use HTTPS-only absolute credential-free URLs, manual bounded redirects, response-size caps, and cross-origin removal of sensitive headers plus explicit Requests `auth=` / `cookies=` arguments.

### 15. Diagnostics became durable

Each GUI session has an ID. Rotating logs record process/job lifecycle and clean exit. Python main-thread/thread exceptions are logged and faulthandler provides a native-fault path where supported.

### 16. The model compatibility layer was hardened

Qt data/setData/header access now defends stale/out-of-range indexes. Production source-aware selection identity is also honored by inherited helper methods, eliminating a state mismatch where checkboxes could be source-aware while helper APIs still looked up a plain ID.

### 17. Repository hygiene was corrected

Tracked `.pyc` / `__pycache__` files were removed and ignored. Earlier generated audit files that had scanned virtual-environment content or contained encoding failures were removed instead of being retained as misleading evidence.

Runtime and development/build requirements are split and constrained.

### 18. Windows packaging is reproducible from the repository

`scripts/build_windows.py` builds one-file GUI and CLI artifacts with PyInstaller, bundled QSS, keyring backends, and keyring metadata.

`scripts/verify_windows.py --build` builds both artifacts, runs the packaged CLI `--help`, and launches the packaged GUI in a private create/close smoke mode before startup scans begin.

## Final executable evidence

The final verification loop reconstructed current GitHub branch files locally and verified their Git object hashes before execution.

Exact current source blobs:

- executor: `63447020d4cfb66188af63290763ff52d0ea3ba3`
- output decoder: `a0301c0419b4ed01742b85501a2b0572bbea40bf`
- bounded command runner: `530c9b0ef766032e226ce69e6b9c6163c6cd5f4e`
- final strict parser: `edc4f1b0712eada3388a96401a1a17505557759c`

Exact current test blobs were also reconstructed for executor, selector controls, decoder, bounded command runner and strict parser.

Fresh final-loop result:

- executor / selector / decoder / command-runner: **50 passed**;
- strict localized parser: **15 passed**;
- total: **65 passed**.

Earlier config and HTTP executable gates remain valid because those validated source/test blobs did not change afterward; final SHA/tree review confirmed continuity.

## Branch/repository state

The final branch remains based on the original `master` merge base and the branch-vs-master comparison reports `behind_by: 0`.

No GitHub Actions workflow was introduced. The large apparent deletions of the historical UI/parser in the diff are moves into compatibility-preserved `legacy_window.py` and `legacy_parser.py`, not discarded application functionality.

## Known residuals

These are not hidden and are intentionally not expanded into risky late rewrites.

### Generic batch completion wording

If one or more packages reach a final failure, the individual failure is logged and the failed row is not removed as success, but the queue can ultimately display the generic `Update complete.` status. This is a usability/reporting issue rather than an update-authority or lifecycle defect.

### HTTPS is not full DNS/IP SSRF isolation

The transport restricts scheme, redirects, body size and credentials, but does not resolve a hostname and reject private/link-local destination IPs. Correct DNS/IP-aware connection policy belongs in a separate networking hardening change; a string blacklist would create false confidence.

### Unknown localized no-update prose fails closed

Known English no-update markers are recognized. An unknown localized no-update sentence without a table is treated as parse failure rather than zero updates. This is intentionally conservative until Winget exposes a structured upgrade result.

## Native acceptance still required

The remaining evidence boundary is real Windows behavior:

- PySide6/QProcess signal ordering;
- pywin32 registry/COM shortcut behavior;
- multiprocessing `spawn` under Windows and frozen builds;
- Windows credential-store/keyring behavior;
- real App Installer/Winget output and process behavior;
- native fault logging;
- packaged PyInstaller startup/teardown.

Run from the exact branch:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python scripts\verify_windows.py --live-winget --build
```

Then perform the manual scenarios in `WINDOWS-VERIFICATION.md`.

## Final recommendation

The code/audit work itself has reached the finish line available from this environment. There is no known release-blocking implementation/static/pure-Python failure left open.

Do **not** merge merely because this report says the implementation audit passed. Run the native Windows gate first. If it passes without exposing a new defect, this branch is ready to merge as the reliability-hardened successor to `master`.

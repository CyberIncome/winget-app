# Winget Universal Dashboard — Reliability Hardening Final Audit Report

Date: 2026-09-01
Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

## Executive verdict

The repository-wide reliability hardening audit is complete.

**Implementation/static/pure-Python audit: PASS.**

**Native Windows acceptance: PASS.**

**Packaged Windows acceptance: PASS.**

**Complete Windows pytest suite: 181/181 PASS.**

**Merge/release recommendation: READY TO MERGE.**

The branch is materially safer than `master` across the crash/hang paths that motivated the audit: background ownership, startup overlap, QProcess state handling, shutdown races, output memory bounds, malformed/localized Winget output, package/source provenance, selector validation, config persistence, redirect credential handling, diagnostics, CLI behavior and build reproducibility.

## Canonical architecture

```text
launcher.py
  -> src.main.main()
     -> RuntimeMainWindow
        -> ProductionMainWindow
           -> HardenedMainWindow
              -> historical MainWindow presentation
```

The historical UI remains in `src/ui/legacy_window.py`; `src/ui/main_window.py` is a compatibility/model shim and direct execution routes back through `src.main`.

The historical parser/inventory implementation remains in `src/logic/legacy_parser.py`; `src/logic/parser.py` is the hardened compatibility facade.

## Major repairs

### Owned background work

The original application used raw daemon threads for long-running work. Production inventory, parsing, detective and API work now use owned spawned-process jobs with one-result envelopes, hard timeouts, cancellation, terminate/join/kill escalation, queue cleanup and lifecycle logging.

### Staged startup

Startup now sequences refresh -> parse -> inventory -> detective -> API instead of overlapping every heavyweight registry/COM/network/process subsystem at launch.

### QProcess lifecycle and shutdown

FailedToStart, CrashExit, watchdog timeout, normal non-zero installer failure and success are distinct states. Crash/timeout do not trigger the one retry without `--silent`.

`RuntimeMainWindow` is the final exception-containment boundary for synchronous refresh/update/watchdog failures and close-time QProcess state/terminate/wait/kill races.

### Watchdog semantics

Quiet output is diagnostic only. Hard termination uses total elapsed time, avoiding false kills of legitimate silent installers.

### Bounded process output

The GUI preserves complete authoritative raw stdout bytes for parsing rather than parsing independently decoded QProcess chunks. The authoritative buffer is capped at 5 MiB and read/overflow failures invalidate the scan.

Live console history is bounded to 2,000 blocks and an unterminated live line is capped at 16 KiB.

CLI non-interactive stdout/stderr capture is disk-backed and capped at 5 MiB per stream. Overflow is explicit failure even if the child exits 0.

### Strict localized Winget parsing

The parser validates the rendered table as a protocol rather than trusting English fixed-character slicing. It supports optional Source, localized headers, CJK/full-width display cells, truncated IDs, malformed/partial-table rejection and a fail-closed Unicode boundary invariant.

Winget remains authoritative about whether an upgrade exists; local numeric version heuristics no longer veto Winget rows.

### Provenance-safe targeting

Source identity travels through display, checkbox identity, package refs, deduplication, exact update commands and row removal. Duplicate IDs from different sources remain distinct and exact commands include `--source` where supplied.

Registry inventory IDs never act as Winget package IDs. Inventory updates require one unique authoritative Winget name match.

Detective-only findings remain informational and cannot independently authorize an update or overwrite Winget's authoritative Available value.

### Selector validation

Package IDs reject display-truncated/trailing-dot forms, leading-dash option-like forms, whitespace/injection-like grammar, ASCII controls and DEL. Names/sources reject control-bearing and option-like values. Commands are argument arrays, never shell strings.

### Config and credentials

Config defaults are deep-copied. Writes use temp file + fsync + atomic replace. Corrupt files are quarantined. Legacy plaintext PAT migration removes plaintext only after secure storage succeeds. PAT edits are debounced and pending state is flushed at shutdown.

### HTTP safety

Remote version requests require absolute HTTPS credential-free URLs, bounded redirects and bounded bodies. Cross-origin redirects remove sensitive headers and explicit Requests `auth=` / `cookies=` values.

### Diagnostics

Every GUI session has an ID. Rotating lifecycle logs, exception hooks, faulthandler and a clean-exit marker provide a durable crash trail.

### Compatibility hardening

Qt model callbacks defend stale/out-of-range indexes. The public model helper APIs share the same source-aware selection contract as the controller.

Old weaker parser/network entry points are now behind the hardened parser facade rather than remaining easy future bypasses.

### Repository/build hygiene

Tracked `.pyc` / `__pycache__` files were removed and broadly ignored. Misleading generated audit artifacts were removed. Runtime and development/build requirements are separated and bounded.

`scripts/build_windows.py` reproducibly builds one-file GUI and CLI executables with the required QSS and keyring packaging support.

## Verification history

The audit deliberately retained failed verification loops instead of presenting an artificially clean history.

Examples:

- selector validation initially admitted a newline-adjacent case; the gate caught it and validation was repaired;
- a new localized parser boundary invariant initially failed 1 of 15 tests because it was too strict for a legitimate German truncated-ID row; it was corrected and rerun 15/15;
- the first Windows aggregate verification exposed a harness-only `ModuleNotFoundError` in direct `scripts/smoke_gui.py` execution; application tests, real Winget, builds and packaged smokes had all passed. The harness was repaired and guarded by a regression invariant, then the Windows gate was rerun successfully.

## Final audit-host evidence

Exact current GitHub blobs were reconstructed and `git hash-object` verified before execution.

Fresh final audit-host results:

- executor / selector / output decoder / bounded command runner: **50 passed**;
- strict localized parser: **15 passed**;
- total: **65 passed**.

## Native Windows acceptance evidence

Accepted environment:

- Windows `10.0.26200.9278`;
- Python `3.12.10`;
- PySide6 `6.11.2`;
- pywin32 `312`;
- requests `2.34.2`;
- click `8.5.0`;
- keyring `25.7.0`;
- pytest `9.1.1`;
- pytest-qt `4.5.0`;
- Ruff `0.16.5`;
- PyInstaller `6.22.2`;
- Winget `v1.29.290`.

Final Windows rerun:

```text
compile all Python sources                    PASS
Ruff correctness lint                         PASS
native Windows lifecycle integration          19 passed
full pytest / pytest-qt suite                 181 passed
source CLI smoke                              PASS
RuntimeMainWindow create/close smoke          PASS
winget --version                              PASS (v1.29.290)
real read-only Winget update scan             PASS
aggregate verdict                             PASSED
```

The immediately preceding build-enabled Windows run also established:

```text
PyInstaller GUI build                         PASS
PyInstaller CLI build                         PASS
packaged CLI --help                           PASS
packaged GUI create/close                     PASS
```

The only source changes after that successful packaged build were the direct smoke-test repository-root bootstrap plus its test/documentation. Application and packaging sources were unchanged, so the packaged evidence applies to the accepted application code.

## Branch/repository state

The audit branch remains based on the original `master` merge base. Final comparison must remain `behind_by: 0` before merge.

No GitHub Actions workflow was introduced. Historical parser/UI implementations are compatibility-preserved rather than discarded.

## Residual follow-up opportunities

No known release-blocking reliability defect remains open from this audit.

Two conservative boundaries remain suitable for future work:

1. HTTPS policy is not full DNS/IP-level private-network SSRF isolation. A correct solution should resolve destinations and enforce private/link-local policy rather than use string blacklists.
2. Unknown localized no-update prose without a table fails closed unless it matches a known marker. This is preferable to falsely claiming zero updates until Winget exposes a structured upgrade result.

A previously recorded batch-status residual was removed after final call-chain verification showed `set_ui_busy(..., busy=False, ...)` resets the visible status to `Ready`; the unused `Update complete.` argument is not presented to the user on that path.

## Final recommendation

The Ferrox-style audit/repair/verify loop is closed.

The implementation passed local exact-blob verification, native Windows lifecycle tests, the complete Windows pytest suite, a real read-only Winget scan, reproducible PyInstaller builds and packaged GUI/CLI smoke tests.

**This branch is ready to merge into `master`.**

The manual exploratory scenarios in `WINDOWS-VERIFICATION.md` remain useful for future release QA, but there is no open deterministic/native acceptance failure blocking this reliability-hardening branch.
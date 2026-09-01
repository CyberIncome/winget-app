# Reliability Hardening Verification

Status: **RELEASE ACCEPTANCE PASSED**

Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

This is the evidence ledger for the reliability-hardening branch. Code changes are not accepted as evidence by themselves. The branch went through repeated audit -> repair -> rerun loops, including failures in hardening code and in the verification harness itself.

## Current architecture contract

Canonical GUI path:

`launcher.py -> src.main.main() -> RuntimeMainWindow -> ProductionMainWindow -> HardenedMainWindow -> historical MainWindow presentation`

`RuntimeMainWindow` is the final release-facing QProcess/shutdown boundary. `ProductionMainWindow` owns package provenance and process-protocol guards. `HardenedMainWindow` owns staged startup and managed spawned jobs. `src/ui/main_window.py` is a compatibility/model shim and direct execution routes back through `src.main`.

## Final must-have ledger

| Must-have | Status | Evidence |
| --- | --- | --- |
| No untracked production daemon threads | PASS | Production inheritance overrides legacy thread-launch paths; static contract tests enforce this. |
| Spawned jobs have timeout/cancel/cleanup | PASS | Owned spawn jobs plus native Windows lifecycle tests. |
| Final shutdown contains process teardown failures | PASS | Hostile-QProcess tests and native Windows close-during-owned-work tests passed. |
| Startup is staged | PASS | refresh -> parse -> inventory -> detective -> API. |
| QProcess outcomes are distinct | PASS | FailedToStart, CrashExit, timeout, normal failure and success are separately handled and covered by Windows tests. |
| Crash/timeout never becomes silent retry | PASS | Retry is limited to normal non-zero installer failure; Windows lifecycle tests passed. |
| Watchdog does not kill only because output is quiet | PASS | Idle output only warns; hard timeout uses total elapsed time. |
| Foreground operations are mutually excluded | PASS | Controller guards plus full Windows pytest suite. |
| Refresh protocol output is bounded/fail-closed | PASS | 5 MiB authoritative raw stdout cap; read/overflow invalidates the scan. |
| Live console memory is bounded | PASS | 2,000 console blocks and 16 KiB live-line cap. |
| CLI captured output is bounded | PASS | Disk-backed 5 MiB per-stream capture and explicit overflow failure. |
| Malformed/partial Winget tables fail closed | PASS | Exact parser tests and live Winget scan passed. |
| Localized/CJK table layout is handled safely | PASS | German/CJK/Unicode-width regression tests passed. |
| Package/source provenance is retained | PASS | Source-aware model/ref/dedup/command/removal behavior covered by tests. |
| Registry inventory IDs are never Winget authority | PASS | Unique authoritative Winget-name mapping; collision regression test passed. |
| Detective-only findings cannot become update authority | PASS | Detective rows remain informational unless backed by Winget authority. |
| Package selectors reject ambiguous/control values | PASS | Truncation, leading-dash, control-character and invalid-grammar cases covered. |
| Config defaults/writes are safe | PASS | Deep-copy, atomic replace, corrupt quarantine and PAT migration tests passed. |
| PAT edits are debounced and flushed on close | PASS | Qt close/debounce coverage passed on Windows. |
| HTTPS redirects/body/credentials are bounded | PASS | Native remote-version suite plus transport tests passed. |
| Session/crash diagnostics are installed | PASS | Session IDs, rotating logs, exception hooks, faulthandler and clean-exit path are present and GUI smoke passed. |
| Runtime/dev/build dependencies are separated/bounded | PASS | Requirements split and dependency versions recorded by Windows verifier. |
| Packaged build is reproducible | PASS | Both one-file artifacts built; packaged CLI and GUI smoke passed. |
| No tracked bytecode / no required GitHub Actions | PASS | Final tree/diff inspection; no CI workflow required. |

## Audit-host exact-blob evidence

Before Windows acceptance, current branch files were reconstructed from GitHub and checked with `git hash-object` before execution.

Fresh final audit-host results:

- executor / selector / decoder / bounded command-runner gate: **50 passed**;
- strict localized Winget parser gate: **15 passed**;
- total exact-current-blob tests: **65 passed**.

The parser gate initially failed 14/15 after a new Unicode boundary invariant proved too strict for a legitimate German truncated-ID fixture. The invariant was corrected, the Git blob reverified, and the entire parser suite reran 15/15.

## Native Windows acceptance — PASS

Acceptance environment:

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

### First Windows run

`python scripts\verify_windows.py --live-winget --build`

Passed:

- compile all Python sources;
- Ruff correctness checks;
- native lifecycle integration: **19 passed**;
- complete pytest suite: **180 passed**;
- source CLI smoke;
- real `winget --version`;
- real read-only Winget update scan;
- PyInstaller GUI + CLI builds;
- packaged CLI smoke;
- packaged GUI create/close smoke.

One check failed before importing application code: direct execution of `scripts/smoke_gui.py` did not put the repository root on `sys.path`. That verification-harness defect was fixed and a source-contract regression test was added.

### Final Windows rerun

After pulling the smoke-harness repair:

`python scripts\smoke_gui.py` -> **PASS**

`python scripts\verify_windows.py --live-winget` -> **ALL REQUESTED CHECKS PASSED**

Final rerun details:

- compile all Python sources: **PASS**;
- Ruff correctness checks: **PASS**;
- native lifecycle integration: **19 passed in 5.25s**;
- complete pytest/pytest-qt suite: **181 passed in 18.53s**;
- source CLI `--help`: **PASS**;
- canonical runtime GUI create/close smoke: **PASS**;
- `winget --version` (`v1.29.290`): **PASS**;
- real read-only Winget update scan: **PASS**;
- aggregate verdict: **PASSED: all requested verification checks succeeded**.

The application/build sources did not change between the successful `--build` run and the final rerun. A GitHub compare from the build-tested head `0195f6a90f4f357fbcdaf640166d7598b194614c` to the post-repair head showed only:

- `scripts/smoke_gui.py`;
- `tests/test_hardened_source.py`;
- verification documentation.

Therefore the previously successful packaged GUI/CLI build and packaged launch evidence remains applicable to the accepted application code.

## Repository-state evidence

Final integrity checks require:

- branch remains ahead of `master` with `behind_by: 0`;
- merge base remains `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`;
- no GitHub Actions workflow is introduced;
- no tracked Python bytecode/cache artifacts are reintroduced;
- the draft PR remains mergeable after final documentation commits.

## Residuals / follow-up opportunities

No known release-blocking reliability defect remains open from this audit.

Two intentionally conservative boundaries remain documented:

- HTTPS safety is not DNS/IP-level private-network SSRF isolation. Adding robust hostname resolution and private/link-local destination policy should be a separate networking hardening change, not a string blacklist.
- Unknown localized no-update prose without a table fails closed unless it matches a known marker. This is preferable to falsely reporting zero updates until Winget exposes a structured upgrade result.

The earlier note claiming a failed batch could visibly end with `Update complete.` was removed after the final call-chain audit showed `set_ui_busy(..., busy=False, ...)` resets the visible status to `Ready`; the status argument is not displayed on that path.

## Final verdict

- implementation/static/pure-Python audit: **PASS**;
- native Windows acceptance: **PASS**;
- complete Windows pytest suite: **181/181 PASS**;
- real read-only Winget integration: **PASS**;
- packaged Windows build: **PASS**;
- packaged CLI smoke: **PASS**;
- packaged GUI smoke: **PASS**;
- release recommendation: **READY TO MERGE**.

Manual crash-boundary exercises in `WINDOWS-VERIFICATION.md` remain useful optional exploratory checks, but the deterministic/native acceptance gate and packaged smoke gate have passed.
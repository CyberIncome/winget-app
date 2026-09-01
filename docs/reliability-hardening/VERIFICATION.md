# Reliability Hardening Verification

Status: **IMPLEMENTATION / STATIC / PURE-PYTHON AUDIT COMPLETE — NATIVE WINDOWS ACCEPTANCE REPAIR LOOP, RERUN PENDING**

Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

This is the evidence ledger for the reliability-hardening branch. Code changes are not accepted as evidence by themselves. A changed blob must either earn fresh executable/static evidence or remain explicitly `WINDOWS-VERIFY` when the required boundary cannot be exercised on the audit host.

## Current architecture contract

Canonical GUI path:

`launcher.py -> src.main.main() -> RuntimeMainWindow -> ProductionMainWindow -> HardenedMainWindow -> historical MainWindow presentation`

`RuntimeMainWindow` is the final release-facing QProcess/shutdown boundary. `ProductionMainWindow` owns package provenance and process-protocol guards. `HardenedMainWindow` owns staged startup and managed spawned jobs. `src/ui/main_window.py` is a compatibility/model shim and direct execution routes back through `src.main`.

## Must-have ledger

| Must-have | Status | Evidence |
| --- | --- | --- |
| No untracked production daemon threads | VERIFIED | Production inheritance overrides the legacy thread-launch paths; static contract test enumerates them. |
| Spawned jobs have timeout/cancel/cleanup | VERIFIED + WINDOWS | `ManagedProcessJob` uses owned spawn processes, one-result envelopes, bounded timeout, terminate/join/kill/close escalation, and queue cleanup. First native Windows lifecycle run passed. |
| Final shutdown contains child/process teardown failures | VERIFIED + WINDOWS | `RuntimeMainWindow` contains state/terminate/wait/kill failures and cancels managed jobs; hostile-QProcess tests and real Windows close-during-spawn tests passed in the native lifecycle run. |
| Startup is staged | VERIFIED | refresh -> parse -> inventory -> detective -> API. |
| QProcess outcomes are distinct | VERIFIED + WINDOWS | FailedToStart, CrashExit, watchdog timeout, normal non-zero failure, and success have separate state paths; native lifecycle tests passed. |
| Crash/timeout never becomes silent retry | VERIFIED + WINDOWS | Retry predicate permits only normal non-zero installer failure; native crash/kill/timeout tests passed. |
| Watchdog does not kill only because output is quiet | VERIFIED | Idle time only logs; hard termination uses total elapsed deadline. |
| Foreground operations are mutually excluded | VERIFIED + WINDOWS | Production blocks overlapping refresh/inventory/update foreground requests; the full Windows pytest suite passed. |
| Refresh protocol output is bounded and fail-closed | VERIFIED + WINDOWS | GUI retains at most 5 MiB authoritative stdout bytes; read/overflow invalidates the scan instead of parsing a truncated table. Full Windows pytest suite passed. |
| Live console memory is bounded | VERIFIED + WINDOWS | Canonical runtime retains 2,000 console blocks and production bounds a never-terminated live line to 16 KiB. Full Windows pytest suite passed. |
| CLI captured output is bounded | VERIFIED + WINDOWS | Disk-backed stdout/stderr capture, 5 MiB per stream, overflow is explicit non-success; full Windows pytest suite passed. |
| Malformed/partial Winget tables fail closed | VERIFIED | Current exact parser test blob passes malformed, partial, empty, localized and Unicode-width cases. |
| Localized/CJK table layout is handled safely | VERIFIED | Display-cell parser passes German and CJK fixtures and rejects a simulated ambiguous-width boundary shift. |
| Package/source provenance is retained | VERIFIED + WINDOWS | Source participates in checkbox identity, refs, deduplication, exact commands and row removal; full Windows pytest suite passed. |
| Registry inventory IDs are never Winget authority | VERIFIED + WINDOWS | Inventory update mapping ignores registry IDs and requires a unique authoritative Winget-name match; full Windows pytest suite passed. |
| Detective-only findings cannot become update authority | VERIFIED + WINDOWS | Detective rows are tagged informational and excluded from executable refs unless independently backed by current Winget output; Windows tests passed. |
| Package selectors reject ambiguous/control values | VERIFIED | IDs reject truncation, leading dash, ASCII controls and invalid grammar; names/sources reject option-like/control values. |
| Config defaults/writes are safe | VERIFIED by unchanged validated blobs | Deep-copy state, atomic temp+fsync+replace, corrupt quarantine and guarded PAT migration. |
| PAT edits are debounced and flushed on close | VERIFIED + WINDOWS tests | Qt debounce plus final runtime close flush is covered by the passing Windows suite; manual credential-store interaction remains a manual acceptance scenario. |
| HTTPS redirects/body/credentials are bounded | VERIFIED + WINDOWS tests | HTTPS-only absolute URLs, redirect/body caps, cross-origin secret header/auth/cookie stripping; native remote-version suite passed. |
| Session/crash diagnostics exist | WINDOWS manual | Session IDs, rotating logs, exception hooks and faulthandler are implemented; real crash-log production remains a manual scenario. |
| Runtime/dev/build dependencies are separated and bounded | VERIFIED | `requirements.txt` and `requirements-dev.txt`; PyInstaller is dev-only. |
| Packaged build is reproducible from repo tooling | VERIFIED + WINDOWS BUILD | First Windows acceptance attempt built both one-file artifacts successfully; packaged CLI and packaged GUI smoke both passed. |
| No tracked bytecode / no required GitHub Actions | VERIFIED | Recursive tree/diff inspection; caches removed/ignored and no workflow is required. |

## Fresh current-blob executable evidence — 2026-09-01

The audit host cannot access GitHub through shell DNS, so current branch files were read through the connected GitHub repository interface, reconstructed locally, and checked with `git hash-object` before execution.

Current source blobs reconstructed and hash-matched exactly:

- `src/logic/executor.py` -> `63447020d4cfb66188af63290763ff52d0ea3ba3`
- `src/logic/output_decode.py` -> `a0301c0419b4ed01742b85501a2b0572bbea40bf`
- `src/logic/command_runner.py` -> `530c9b0ef766032e226ce69e6b9c6163c6cd5f4e`
- `src/logic/upgrade_parser.py` -> `edc4f1b0712eada3388a96401a1a17505557759c`

Current test blobs hash-matched exactly before execution:

- `tests/test_executor.py` -> `3d49f0a432189c822306133416563c02612230b3`
- `tests/test_executor_controls.py` -> `4042346eedf233243e84868417b4be9383beeccd`
- `tests/test_output_decode.py` -> `fc9d5ecb83b611866e5bb5444032c886208b9988`
- `tests/test_command_runner.py` -> `5393150961bd0d856ca24d4d70a33209938c5051`
- `tests/test_upgrade_parser.py` -> `13aa9c28e1d174f0fd7e2148ab1e3d5da1e7ccfd`

Fresh results:

- executor / selector / decoder / bounded command-runner gate: **50 passed**;
- strict localized Winget parser gate after final repair: **15 passed**;
- total fresh exact-current-blob tests in the final audit-host loop: **65 passed**.

The final parser gate was intentionally **not** green on its first run: 14 passed / 1 failed because an over-strict new column-boundary invariant rejected the legitimate German truncated-ID fixture. The invariant was repaired to reject only boundaries that split two adjacent non-space characters. The updated parser source hash matched GitHub and the full exact parser suite then passed 15/15. This failure/repair is retained as verification evidence rather than hidden.

Earlier pure-Python config and HTTP gates remain applicable because those source/test blobs did not change afterward; the final tree SHA continuity check confirmed those validated modules were unchanged.

## First native Windows acceptance attempt — 2026-09-01

Environment supplied by the Windows acceptance run:

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

Results from `python scripts\verify_windows.py --live-winget --build`:

- compile all Python sources: **PASS**;
- Ruff correctness checks: **PASS**;
- native Windows lifecycle integration: **19 passed**;
- complete pytest/pytest-qt suite: **180 passed**;
- source CLI `--help` smoke: **PASS**;
- direct `scripts/smoke_gui.py`: **FAILED** before application import because Python set `scripts` rather than the repository root as `sys.path[0]`;
- `winget --version`: **PASS**;
- real read-only Winget update scan: **PASS**;
- PyInstaller GUI + CLI build: **PASS**;
- packaged CLI smoke: **PASS**;
- packaged GUI create/close smoke: **PASS**.

The one failed check was therefore a defect in the verification harness, not a failed application/runtime boundary. `scripts/smoke_gui.py` now inserts its repository root into `sys.path` before importing `src`, and `tests/test_hardened_source.py` contains a regression invariant requiring that bootstrap to precede the application import. A rerun from the updated branch is required before the aggregate Windows verdict is changed to PASS.

## Repository-state evidence

A final branch-vs-master comparison reported:

- branch status: ahead of `master`;
- `behind_by: 0`;
- merge base remains `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`;
- no GitHub Actions workflow added;
- tracked Python bytecode/cache artifacts removed;
- major apparent UI/parser deletions are compatibility moves into `legacy_window.py` / `legacy_parser.py`, not discarded functionality.

## Known non-blocking residuals

These are recorded rather than silently expanded into late risky rewrites:

- A batch containing one or more final package failures can still end with the generic status text `Update complete.` after the individual failures were correctly logged. This is a reporting/usability defect, not a targeting or lifecycle failure; failed rows are not removed as successes.
- The bounded HTTPS policy is not full SSRF isolation. It rejects unsafe schemes, credentials and unsafe redirects, but does not resolve hostnames and deny private/link-local destination IPs. A correct DNS/IP-aware policy should be a separate networking hardening change rather than a string blacklist.
- Localized no-update messages are recognized only for known English markers. Unknown localized no-update prose fails closed instead of claiming zero updates. This favors correctness over convenience until Winget exposes a structured upgrade result.

## Required Windows acceptance rerun

Update the local checkout to the latest audit branch, then rerun:

```powershell
git checkout audit/ferrox-reliability-hardening
git pull
python scripts\verify_windows.py --live-winget --build
```

Because the first run already proved both packaged artifacts build and launch, a quicker repair-loop check may first run:

```powershell
python scripts\smoke_gui.py
python -m pytest -q
```

The final acceptance verdict should still come from the full verification command after the branch update.

Until that succeeds:

- implementation/static/pure-Python audit: **PASS**;
- native Windows application tests: **PASS in first run**;
- packaged Windows build/smoke: **PASS in first run**;
- aggregate verification harness: **RERUN PENDING after smoke-path repair**;
- merge/release recommendation: **HOLD UNTIL RERUN PASSES**.

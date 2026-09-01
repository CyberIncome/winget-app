# Reliability Hardening Verification

Status: **IMPLEMENTATION / STATIC / PURE-PYTHON AUDIT COMPLETE — NATIVE WINDOWS ACCEPTANCE PENDING**

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
| Spawned jobs have timeout/cancel/cleanup | VERIFIED + WINDOWS-VERIFY integration | `ManagedProcessJob` uses owned spawn processes, one-result envelopes, bounded timeout, terminate/join/kill/close escalation, and queue cleanup. Native spawn acceptance remains Windows-specific. |
| Final shutdown contains child/process teardown failures | WINDOWS-VERIFY | `RuntimeMainWindow` contains state/terminate/wait/kill failures and cancels managed jobs; hostile-QProcess tests and real Windows close-during-spawn tests are committed. |
| Startup is staged | VERIFIED | refresh -> parse -> inventory -> detective -> API. |
| QProcess outcomes are distinct | WINDOWS-VERIFY | FailedToStart, CrashExit, watchdog timeout, normal non-zero failure, and success have separate state paths; native signal ordering remains Windows evidence. |
| Crash/timeout never becomes silent retry | WINDOWS-VERIFY | Retry predicate permits only normal non-zero installer failure; native tests cover crash/kill/timeout. |
| Watchdog does not kill only because output is quiet | VERIFIED | Idle time only logs; hard termination uses total elapsed deadline. |
| Foreground operations are mutually excluded | VERIFIED + WINDOWS-VERIFY UI | Production blocks overlapping refresh/inventory/update foreground requests; Qt interaction is covered by committed tests. |
| Refresh protocol output is bounded and fail-closed | VERIFIED + WINDOWS-VERIFY QProcess | GUI retains at most 5 MiB authoritative stdout bytes; read/overflow invalidates the scan instead of parsing a truncated table. |
| Live console memory is bounded | VERIFIED + WINDOWS-VERIFY Qt | Canonical runtime retains 2,000 console blocks and production bounds a never-terminated live line to 16 KiB. |
| CLI captured output is bounded | VERIFIED | Disk-backed stdout/stderr capture, 5 MiB per stream, overflow is explicit non-success. |
| Malformed/partial Winget tables fail closed | VERIFIED | Current exact parser test blob passes malformed, partial, empty, localized and Unicode-width cases. |
| Localized/CJK table layout is handled safely | VERIFIED | Display-cell parser passes German and CJK fixtures and rejects a simulated ambiguous-width boundary shift. |
| Package/source provenance is retained | VERIFIED + WINDOWS-VERIFY Qt | Source participates in checkbox identity, refs, deduplication, exact commands and row removal. |
| Registry inventory IDs are never Winget authority | VERIFIED | Inventory update mapping ignores registry IDs and requires a unique authoritative Winget-name match. |
| Detective-only findings cannot become update authority | VERIFIED + WINDOWS-VERIFY Qt | Detective rows are tagged informational and excluded from executable refs unless independently backed by current Winget output. |
| Package selectors reject ambiguous/control values | VERIFIED | IDs reject truncation, leading dash, ASCII controls and invalid grammar; names/sources reject option-like/control values. |
| Config defaults/writes are safe | VERIFIED by unchanged validated blobs | Deep-copy state, atomic temp+fsync+replace, corrupt quarantine and guarded PAT migration. |
| PAT edits are debounced and flushed on close | WINDOWS-VERIFY | Qt debounce plus final runtime close flush; credential-store behavior needs Windows. |
| HTTPS redirects/body/credentials are bounded | VERIFIED by unchanged validated blobs | HTTPS-only absolute URLs, redirect/body caps, cross-origin secret header/auth/cookie stripping. |
| Session/crash diagnostics exist | WINDOWS-VERIFY | Session IDs, rotating logs, exception hooks and faulthandler are implemented; native crash production requires Windows. |
| Runtime/dev/build dependencies are separated and bounded | VERIFIED | `requirements.txt` and `requirements-dev.txt`; PyInstaller is dev-only. |
| Packaged build is reproducible from repo tooling | WINDOWS-VERIFY | `scripts/build_windows.py` creates GUI/CLI one-file artifacts and `verify_windows.py --build` launch-smokes both. |
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
- total fresh exact-current-blob tests in the final loop: **65 passed**.

The final parser gate was intentionally **not** green on its first run: 14 passed / 1 failed because an over-strict new column-boundary invariant rejected the legitimate German truncated-ID fixture. The invariant was repaired to reject only boundaries that split two adjacent non-space characters. The updated parser source hash matched GitHub and the full exact parser suite then passed 15/15. This failure/repair is retained as verification evidence rather than hidden.

Earlier pure-Python config and HTTP gates remain applicable because those source/test blobs did not change afterward; the final tree SHA continuity check confirmed those validated modules were unchanged.

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

## Required Windows acceptance

From this exact branch on Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python scripts\verify_windows.py --live-winget --build
```

Then complete the manual crash-boundary checks in `WINDOWS-VERIFICATION.md`.

Until that succeeds:

- implementation/static/pure-Python audit: **PASS**;
- native Windows acceptance: **PENDING**;
- packaged Windows acceptance: **PENDING**;
- merge/release recommendation: **HOLD FOR WINDOWS ACCEPTANCE**.

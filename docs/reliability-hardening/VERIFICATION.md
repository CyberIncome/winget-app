# Reliability Hardening Verification

Status: **APPLICATION / RUNTIME ACCEPTANCE PASSED — NEW X64 INSTALLER ACCEPTANCE PENDING**

Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

This is the evidence ledger for the reliability-hardening branch. Code changes are not accepted as evidence by themselves. The branch went through repeated audit -> repair -> rerun loops, including failures in hardening code, parser invariants, verification tooling, and now release-packaging review.

## Current architecture contract

Canonical GUI path:

`launcher.py -> src.main.main() -> RuntimeMainWindow -> ProductionMainWindow -> HardenedMainWindow -> historical MainWindow presentation`

`RuntimeMainWindow` is the final release-facing QProcess/shutdown boundary. `ProductionMainWindow` owns package provenance and process-protocol guards. `HardenedMainWindow` owns staged startup and managed spawned jobs. `src/ui/main_window.py` is a compatibility/model shim and direct execution routes back through `src.main`.

## Reliability/runtime must-have ledger

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
| No tracked bytecode / no required GitHub Actions | PASS | Final tree/diff inspection; no CI workflow required. |

## Audit-host exact-blob evidence

Before native acceptance, current application blobs were reconstructed from GitHub and checked with `git hash-object` before execution.

- executor / selector / decoder / bounded command-runner gate: **50 passed**;
- strict localized Winget parser gate: **15 passed**;
- total exact-current application-logic blob tests: **65 passed**.

The parser gate initially failed 14/15 after a Unicode boundary invariant proved too strict for a legitimate German truncated-ID fixture. The invariant was corrected, the Git blob reverified, and the entire parser suite reran 15/15.

## Native Windows application acceptance — PASS

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

Final accepted application rerun:

- compile all Python sources: **PASS**;
- Ruff correctness checks: **PASS**;
- native lifecycle integration: **19 passed in 5.25s**;
- complete pytest/pytest-qt suite: **181 passed in 18.53s**;
- source CLI `--help`: **PASS**;
- canonical runtime GUI create/close smoke: **PASS**;
- `winget --version` (`v1.29.290`): **PASS**;
- real read-only Winget update scan: **PASS**;
- aggregate verdict: **PASSED: all requested verification checks succeeded**.

The earlier PyInstaller-only build also successfully built and smoke-launched both portable executables. That evidence established the pre-installer packaging baseline.

## Post-acceptance Windows x64 installer/release tranche

After the reliability runtime was accepted, the repository was extended with a formal local release/distribution pipeline. This changes packaging/build tooling, so the earlier portable-build result is not being inherited as proof of the new release bundle.

Added release contract:

- `VERSION` is the single semantic release version source; initial value: `1.0.0`;
- PyInstaller GUI and CLI builds receive Windows version resources derived from `VERSION`;
- `installer/WingetUniversalDashboard.iss` provides a stable Inno Setup application identity and per-user installation;
- `SetupArchitecture=x64` requires an actual AMD64 setup loader;
- `ArchitecturesAllowed=x64compatible` and `ArchitecturesInstallIn64BitMode=x64compatible` allow supported x64 environments including Windows 11 ARM64 x64 compatibility;
- the GUI executable, CLI executable, and generated setup executable are all checked as AMD64 PE (`0x8664`) before acceptance;
- the setup installs under `%LOCALAPPDATA%\Programs\WingetUniversalDashboard`, creates a Start Menu shortcut, offers an optional desktop shortcut, and registers an Inno uninstaller;
- release output is `WingetUniversalDashboard-Setup-x64.exe` plus portable GUI/CLI and `SHA256SUMS.txt`;
- optional Authenticode signing uses `signtool`, SHA-256 and an RFC3161 timestamp without storing certificate secrets in the repository;
- `publish_release.py` uses authenticated local `gh`, refuses a dirty worktree, refuses non-`master` publication by default, refuses overwriting an existing version, targets the exact current commit, uploads all four assets, and creates a draft release unless `--publish` is explicitly supplied;
- no GitHub Actions workflow is required.

### Release-tooling audit evidence

The release-tooling contract was tested locally before commit and then reread from the committed branch. The pure tooling suite passed **11/11** before the final metadata correction. The final committed version/installer assertions were rerun after the correction and passed, including:

- stable semantic version parses to numeric `major.minor.patch.0` metadata;
- prerelease text such as `1.2.3-rc.1` remains human-readable while Win32 numeric version fields remain numeric;
- invalid version forms fail closed;
- stable installer `AppId` is retained;
- `SetupArchitecture=x64` is present;
- x64-compatible install-mode directives are present;
- per-user/no-elevation installation is present;
- `VersionInfoVersion` and `VersionInfoProductVersion` use the numeric version while `VersionInfoProductTextVersion` preserves semantic text;
- release builder emits installer + SHA-256 manifest;
- publisher defaults to a draft and requires a clean `master` worktree;
- installer smoke uses a temporary install directory and removes the installed binaries afterward.

The release audit itself found and repaired two defects before native acceptance:

1. `x64compatible` alone would install x64 payloads but Inno Setup 7 would still emit its default x86 setup loader. `SetupArchitecture=x64` was added and the generated setup PE is now mechanically required to be AMD64.
2. semantic prerelease text was initially placed into Inno's numeric `VersionInfoProductVersion`. The installer now uses numeric product/file versions and separate semantic `VersionInfoProductTextVersion`.

### New native installer acceptance — PENDING

The new release/package code modifies `scripts/build_windows.py` and adds the Inno installer. It therefore requires a fresh Windows packaging gate before this extended branch is merged/released.

Install current Inno Setup 7 once if it is not installed:

```powershell
winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
```

Then, after pulling the current audit branch, run:

```powershell
python scripts\verify_windows.py --live-winget --installer
```

`--installer` performs the ordinary deterministic/native gate, rebuilds versioned AMD64 PyInstaller GUI/CLI artifacts, compiles the true x64 Inno setup, smokes the portable artifacts, silently installs the setup into a temporary per-user directory, launches the installed GUI/CLI, silently uninstalls it, and verifies application binaries were removed.

## Residual follow-up opportunities

No known release-blocking application reliability defect remains open from the original audit.

Two conservative application boundaries remain suitable for future work:

- HTTPS safety is not DNS/IP-level private-network SSRF isolation. A correct solution should resolve destinations and enforce private/link-local policy rather than use string blacklists.
- Unknown localized no-update prose without a table fails closed unless it matches a known marker. This is preferable to falsely claiming zero updates until Winget exposes a structured upgrade result.

## Current verdict

- implementation/static/pure-Python application audit: **PASS**;
- native Windows application acceptance: **PASS**;
- complete accepted Windows application pytest suite: **181/181 PASS**;
- real read-only Winget integration: **PASS**;
- release/installer static/pure tooling audit: **PASS**;
- true Windows x64 installer build/install/uninstall acceptance: **PENDING**;
- merge/release recommendation: **HOLD ONLY UNTIL THE NEW INSTALLER GATE PASSES**.

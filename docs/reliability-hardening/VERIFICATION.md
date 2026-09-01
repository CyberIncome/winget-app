# Reliability Hardening Verification

Status: **APPLICATION / RUNTIME ACCEPTANCE PASSED — FINAL X64 INSTALLER ACCEPTANCE PENDING**

Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

This ledger separates already accepted application/runtime evidence from the newer installer/release tranche. Packaging changes do not inherit older packaged-build evidence by assumption.

## Accepted application/runtime contract

Canonical GUI path:

`launcher.py -> src.main.main() -> RuntimeMainWindow -> ProductionMainWindow -> HardenedMainWindow -> historical MainWindow presentation`

The accepted reliability work covers owned spawned jobs, staged startup, bounded process output, explicit QProcess outcomes, deterministic shutdown, fail-closed localized Winget parsing, source-aware update authority, selector validation, atomic config/credential handling, bounded HTTPS behavior, diagnostics, and repository hygiene.

### Audit-host application evidence

- executor / selector / decoder / bounded command runner: **50 passed**;
- strict localized Winget parser: **15 passed**;
- exact-current application logic total: **65 passed**.

The parser gate deliberately retained a failed-first loop: an over-strict Unicode boundary invariant rejected a legitimate German truncated-ID row. It was corrected and the full parser gate reran 15/15.

### Native Windows application acceptance — PASS

Accepted environment included Windows `10.0.26200.9278`, Python `3.12.10`, PySide6 `6.11.2`, pywin32 `312`, pytest `9.1.1`, pytest-qt `4.5.0`, PyInstaller `6.22.2`, and Winget `v1.29.290`.

Final accepted application rerun:

- compile all Python sources: **PASS**;
- Ruff correctness checks: **PASS**;
- native lifecycle integration: **19 passed in 5.25s**;
- complete pytest/pytest-qt suite at that accepted application head: **181 passed in 18.53s**;
- source CLI smoke: **PASS**;
- canonical runtime GUI create/close smoke: **PASS**;
- real `winget --version`: **PASS**;
- real read-only Winget update scan: **PASS**;
- aggregate verdict: **PASSED: all requested verification checks succeeded**.

Earlier portable PyInstaller GUI/CLI builds and packaged launch smokes also passed before the installer/release tranche was introduced.

## Final Windows x64 installer/release contract

The post-acceptance release tranche now provides:

- root `VERSION` as the single SemVer source, initially `1.0.0`;
- numeric Win32 version resources plus human-readable semantic version text;
- AMD64 PyInstaller GUI and CLI executables;
- Inno Setup 7 installer with `SetupArchitecture=x64`;
- `x64compatible` architecture/install-mode support;
- per-user install under `%LOCALAPPDATA%\Programs\WingetUniversalDashboard`;
- stable `AppId`, normal uninstall registration, Start Menu shortcut and optional desktop shortcut;
- `BUILD_INFO.json` recording exact version, Git commit and clean/dirty build state;
- AMD64 PE verification for GUI, CLI and setup executable;
- SHA-256 manifest covering setup, GUI, CLI and `BUILD_INFO.json`;
- optional Authenticode signing before final checksum generation;
- local GitHub Release publishing through authenticated `gh`, with no Actions dependency.

### Release-integrity protections

The final release pipeline refuses:

- release builds from a dirty worktree;
- reused binaries whose `BUILD_INFO.json` version or commit differs from the current source;
- any `BUILD_INFO.json` marked `dirty: true`;
- non-AMD64 GUI, CLI or setup executables;
- checksum mismatches after signing/building;
- an Inno compiler that does not identify as Inno Setup 7;
- publishing from detached HEAD;
- non-`master` publication unless explicitly allowed;
- a local release branch whose HEAD differs from pushed `origin/<branch>`;
- an already-used remote version tag or GitHub Release.

Semantic prerelease versions and intentional non-master test releases are automatically marked prerelease. Releases are created as drafts unless `--publish` is explicitly supplied.

The release uploads five assets:

```text
WingetUniversalDashboard-Setup-x64.exe
WingetUniversalDashboard.exe
WingetUniversalDashboardCLI.exe
BUILD_INFO.json
SHA256SUMS.txt
```

`SHA256SUMS.txt` hashes the first four items, including the source-provenance file.

### Installer smoke safety

The installer acceptance smoke:

1. refuses to run if a normal Winget Universal Dashboard installation or matching HKCU uninstall entry already exists;
2. silently installs to a temporary directory with no shortcuts;
3. verifies GUI, CLI and `BUILD_INFO.json` were installed;
4. runs installed CLI `--help`;
5. constructs/closes the installed GUI in packaged-smoke mode;
6. silently uninstalls;
7. verifies installed files and the temporary HKCU uninstall entry were removed.

### Pure release-tooling evidence — PASS

The final tested release-tooling contract passed **21/21** locally before the exact tested blobs were committed.

Coverage includes:

- SemVer and Windows numeric-version bounds;
- prerelease detection;
- exact clean version+commit build identity;
- dirty-build rejection;
- SHA-256 tamper detection;
- true-x64 Inno directives;
- source-bound release builds;
- Inno Setup 7 enforcement;
- pushed-HEAD/tag/publisher guards;
- installer-smoke existing-install protection and uninstall cleanup.

The exact committed release core and test blobs were reread after landing; for example `scripts/release_common.py` is blob `11ffd9de043eae50158d2ca4def81bbb4654178e` and `tests/test_release_tooling.py` is blob `5486bb8ab56668ef25fe26287568e83b40c190b0`.

## Release-specific repair history

The installer audit found and repaired several defects before native acceptance:

1. `x64compatible` install mode alone still allowed Inno's default x86 setup loader; `SetupArchitecture=x64` plus PE verification now require a true AMD64 setup executable.
2. semantic prerelease text was initially used in a numeric Inno version field; numeric and human-readable product versions are now separated.
3. version-only stale-artifact detection was insufficient; release identity is now bound to exact Git commit and clean-tree state.
4. checksum generation alone was insufficient; publishing now recomputes and verifies the checksum manifest.
5. a temporary installer smoke could have interfered with an existing normal install's uninstall identity; it now refuses to run when an existing install is detected.

## Final native installer acceptance — PENDING

Install current 64-bit Inno Setup 7 once if necessary:

```powershell
winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
```

Then update the clean audit branch and run:

```powershell
python scripts\verify_windows.py --live-winget --installer
```

That command reruns the deterministic/native application checks, rebuilds source-bound AMD64 portable artifacts, compiles/verifies the true x64 setup, verifies checksums, smokes portable GUI/CLI, installs the setup to a temporary location, smokes the installed GUI/CLI, uninstalls, and verifies cleanup.

## Current verdict

- application/static/pure-Python reliability audit: **PASS**;
- native Windows application acceptance: **PASS**;
- real read-only Winget integration: **PASS**;
- final installer/release pure tooling contract: **21/21 PASS**;
- true x64 installer build/install/uninstall acceptance: **PENDING**;
- merge/release recommendation: **HOLD ONLY UNTIL THE INSTALLER GATE PASSES**.

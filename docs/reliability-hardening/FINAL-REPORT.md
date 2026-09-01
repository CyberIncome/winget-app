# Winget Universal Dashboard — Reliability Hardening Final Audit Report

Date: 2026-09-01
Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

## Executive verdict

The repository-wide reliability hardening audit is complete and the application/runtime itself has passed native Windows acceptance.

**Implementation/static/pure-Python application audit: PASS.**

**Native Windows application acceptance: PASS.**

**Complete accepted Windows application pytest suite: 181/181 PASS.**

A post-acceptance extension now adds a formal Windows x64 installer and GitHub Release pipeline. Because that extension changes `scripts/build_windows.py` and adds a new Inno Setup packaging layer, its final native packaging evidence must be earned separately.

**Windows x64 installer static/pure tooling audit: PASS.**

**Windows x64 installer build/install/uninstall acceptance: PENDING.**

**Current merge/release recommendation: HOLD ONLY UNTIL THE INSTALLER ACCEPTANCE COMMAND PASSES.**

## Canonical application architecture

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

## Reliability repairs completed

The accepted reliability branch provides:

- owned spawned-process background work with timeout/cancel/terminate/join/kill cleanup;
- staged startup instead of overlapping heavy registry/COM/network work;
- distinct QProcess FailedToStart/crash/timeout/normal-failure/success handling;
- `RuntimeMainWindow` containment for synchronous QProcess and shutdown wrapper/handle failures;
- hard elapsed watchdog timeouts while output silence is diagnostic only;
- bounded raw GUI refresh output, bounded live console state, and bounded disk-backed CLI capture;
- strict fail-closed localized/CJK-aware Winget table parsing;
- source-aware package selection, deduplication, command construction and row removal;
- protection against registry IDs or detective-only rows becoming Winget update authority;
- fail-closed package/name/source selector validation;
- atomic configuration persistence and secure PAT migration/debounce/close flushing;
- HTTPS-only bounded redirect/body handling with cross-origin credential stripping;
- durable session/crash diagnostics;
- stale-index-safe Qt model callbacks;
- removal of tracked bytecode/cache artifacts and separation of runtime/dev dependencies.

## Accepted application evidence

Audit-host exact-current application logic gates passed:

- executor / selector / output decoder / bounded command runner: **50 passed**;
- strict localized parser: **15 passed**;
- total: **65 passed**.

Native Windows acceptance environment included Windows `10.0.26200.9278`, Python `3.12.10`, PySide6 `6.11.2`, pywin32 `312`, pytest `9.1.1`, pytest-qt `4.5.0`, PyInstaller `6.22.2`, and Winget `v1.29.290`.

Final accepted Windows application run:

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

The verification history intentionally retained failures that improved the branch, including an early selector-validation bug, an over-strict Unicode parser invariant, and a direct-script smoke harness import-path defect.

## Windows x64 installer and release pipeline

The post-acceptance release tranche adds:

```text
VERSION
  -> PyInstaller GUI/CLI Windows version resources
  -> AMD64 portable GUI + CLI executables
  -> Inno Setup 7 true x64 installer
  -> SHA256SUMS.txt
  -> optional Authenticode signing
  -> local GitHub Release publication through gh
```

### Single-source versioning

`VERSION` is the release version source; initial value is `1.0.0`. Semantic text is retained for human-facing metadata while Windows numeric fields use `major.minor.patch.0`.

### True x64 packaging

The installer uses:

- `SetupArchitecture=x64` so the setup executable itself is AMD64;
- `ArchitecturesAllowed=x64compatible`;
- `ArchitecturesInstallIn64BitMode=x64compatible`;
- mechanical PE-machine verification (`0x8664`) for GUI, CLI and setup output.

This distinction was found during the release-specific adversarial pass: x64 install mode alone does not make the Inno setup loader itself 64-bit.

### Installer behavior

The Inno installer:

- installs per-user to `%LOCALAPPDATA%\Programs\WingetUniversalDashboard` without requiring elevation;
- bundles the GUI and CLI;
- has a stable `AppId` for upgrades/uninstall identity;
- creates a Start Menu shortcut;
- offers an optional desktop shortcut;
- preserves user config/keyring state outside the install directory;
- supports silent installation/uninstallation used by acceptance testing;
- outputs `dist\WingetUniversalDashboard-Setup-x64.exe`.

### Release assets

`python scripts\build_release.py` produces:

```text
dist\WingetUniversalDashboard-Setup-x64.exe
dist\WingetUniversalDashboard.exe
dist\WingetUniversalDashboardCLI.exe
dist\SHA256SUMS.txt
```

### Signing

`python scripts\build_release.py --sign` optionally signs GUI/CLI before installer creation and the installer afterward. Signing is driven by environment configuration (`WUD_SIGN_CERT_SHA1`, optional `SIGNTOOL_EXE` and timestamp URL); certificate secrets are not stored in the repository. Each signature is verified with `signtool verify /pa`.

Unsigned builds remain functional but may show Windows Unknown Publisher/SmartScreen reputation warnings.

### GitHub Releases

`scripts/publish_release.py` publishes locally with authenticated GitHub CLI, not Actions. It:

- refuses dirty working trees;
- refuses non-`master` publication by default;
- reads the tag from `VERSION` (`v<VERSION>`);
- targets the exact current commit;
- refuses to overwrite an existing release version;
- uploads setup, portable GUI, portable CLI and SHA-256 manifest;
- creates a **draft release by default**; publication requires explicit `--publish`.

The repository had no GitHub Releases before this pipeline was added, so `1.0.0` is configured as the first formal version.

## Release-tooling verification history

The pure release-tooling suite passed **11/11** before the final metadata correction. The committed final installer/version contract was then reread and the affected assertions rerun successfully.

The release-specific adversarial pass found and repaired:

1. the initial Inno configuration produced x64 install mode but did not explicitly require a 64-bit setup loader; `SetupArchitecture=x64` plus post-build PE verification now enforce a true x64 setup;
2. semantic prerelease text initially fed Inno's numeric `VersionInfoProductVersion`; numeric file/product versions and semantic `VersionInfoProductTextVersion` are now separated.

## Native installer acceptance required

The application runtime has already passed Windows acceptance. The **new release/package layer** now needs one final native gate because it changes packaging behavior.

Install current Inno Setup 7 if needed:

```powershell
winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
```

Then pull this branch and run:

```powershell
python scripts\verify_windows.py --live-winget --installer
```

That gate:

1. reruns compilation, Ruff, native lifecycle tests and the full suite;
2. reruns the live read-only Winget check;
3. rebuilds versioned AMD64 GUI and CLI executables;
4. compiles and verifies a true AMD64 Inno setup executable;
5. smoke-launches portable GUI/CLI;
6. silently installs the setup into a temporary per-user directory;
7. smoke-launches the **installed** GUI/CLI;
8. silently uninstalls it;
9. verifies the installed application binaries are removed.

## Residual application follow-up opportunities

No known release-blocking application reliability defect remains open.

Two conservative future-hardening opportunities remain:

1. HTTPS policy is not full DNS/IP-level private-network SSRF isolation.
2. Unknown localized no-update prose without a table fails closed unless it matches a known marker.

## Current recommendation

The original Ferrox-style reliability audit remains **PASS** and its native application evidence remains valid.

The newly added release pipeline is fully wired and statically/purely audited, but the new build/installer artifacts have not yet been produced by the current branch on Windows.

**Run `python scripts\verify_windows.py --live-winget --installer`. If it passes, the installer/release tranche can be marked accepted and this branch returns to READY TO MERGE.**

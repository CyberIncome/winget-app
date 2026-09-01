# Winget Universal Dashboard — Reliability Hardening Final Audit Report

Date: 2026-09-01
Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

## Executive verdict

The repository-wide application reliability audit is complete and the application/runtime has passed native Windows acceptance.

**Application/static/pure-Python audit: PASS.**

**Native Windows application acceptance: PASS.**

**Accepted Windows application pytest suite: 181/181 PASS at the accepted runtime head.**

A post-acceptance extension adds a formal Windows x64 installer and local GitHub Release pipeline. That release layer has passed its final pure tooling contract but has not yet been compiled/installed/uninstalled from the current branch on Windows.

**Final installer/release pure tooling contract: 21/21 PASS.**

**True Windows x64 installer build/install/uninstall acceptance: PENDING.**

**Current recommendation: HOLD MERGE ONLY UNTIL THE INSTALLER ACCEPTANCE COMMAND PASSES.**

## Accepted application architecture

```text
launcher.py
  -> src.main.main()
     -> RuntimeMainWindow
        -> ProductionMainWindow
           -> HardenedMainWindow
              -> historical MainWindow presentation
```

The accepted reliability work includes owned background processes, staged startup, explicit QProcess outcomes, bounded process output, deterministic shutdown, strict localized Winget parsing, source-aware update authority, selector validation, atomic config/credential handling, bounded HTTPS behavior, durable diagnostics and repository hygiene.

Native Windows acceptance already established compile/Ruff PASS, 19 native lifecycle tests, 181 application tests, source CLI smoke, canonical GUI create/close smoke, real Winget v1.29.290 integration, and an aggregate PASS. Portable PyInstaller GUI/CLI builds and smokes also passed before the installer tranche was introduced.

## Final Windows x64 release architecture

```text
VERSION
  -> versioned AMD64 PyInstaller GUI + CLI
  -> BUILD_INFO.json (VERSION + exact Git commit + dirty flag)
  -> Inno Setup 7 true AMD64 installer
  -> optional Authenticode signing
  -> SHA256SUMS.txt
  -> local GitHub Release publication through gh
```

### True x64 installer

The Inno Setup definition uses:

- `SetupArchitecture=x64`, requiring an AMD64 setup executable;
- `ArchitecturesAllowed=x64compatible`;
- `ArchitecturesInstallIn64BitMode=x64compatible`;
- a stable `AppId` for upgrade/uninstall identity;
- per-user installation under `%LOCALAPPDATA%\Programs\WingetUniversalDashboard`;
- Start Menu shortcut plus optional desktop shortcut;
- bundled GUI, CLI and `BUILD_INFO.json`.

The build tooling mechanically parses PE headers and refuses GUI, CLI or setup executables whose machine type is not AMD64 (`0x8664`). It also verifies that the selected command-line compiler identifies as Inno Setup 7.

### Source-bound release provenance

Release artifacts are bound to the exact source they came from.

`dist\BUILD_INFO.json` records:

- semantic `VERSION`;
- exact Git commit SHA;
- whether the worktree was dirty when the portable binaries were built.

Complete release builds require a clean worktree. Installer creation and publication refuse a build identity that is dirty, stale, wrong-version or from a different commit.

`SHA256SUMS.txt` covers:

```text
WingetUniversalDashboard-Setup-x64.exe
WingetUniversalDashboard.exe
WingetUniversalDashboardCLI.exe
BUILD_INFO.json
```

The publisher recomputes and verifies the manifest before upload.

### Versioning

The root `VERSION` file is the single human release-version source, initially `1.0.0`.

Semantic versions may include prerelease/build metadata. Windows numeric resources remain numeric (`major.minor.patch.0`) while semantic text is retained in human-readable product metadata. Numeric Windows components above 65535 and invalid SemVer forms fail closed.

Semantic prereleases automatically become GitHub prereleases.

### Installer acceptance safety

The native installer smoke is deliberately isolated:

- it refuses to run when a normal Winget Universal Dashboard install directory or matching HKCU uninstall entry already exists;
- it installs silently into a temporary directory with shortcuts disabled;
- it verifies GUI, CLI and build identity were installed;
- it smoke-launches installed GUI/CLI;
- it silently uninstalls;
- it verifies application files and temporary uninstall registration are removed.

This prevents release QA from silently replacing or unregistering a user's real installation.

### GitHub Release publishing

Publishing is local through authenticated GitHub CLI; no GitHub Actions workflow is required.

`scripts/publish_release.py` refuses:

- dirty working trees;
- detached HEAD;
- non-`master` publication unless explicitly allowed;
- local HEAD that differs from pushed `origin/<branch>`;
- source identity mismatches;
- checksum mismatches;
- non-AMD64 binaries;
- an existing remote version tag;
- an existing GitHub Release with the same version.

It creates a **draft** release by default and uploads five assets:

```text
WingetUniversalDashboard-Setup-x64.exe
WingetUniversalDashboard.exe
WingetUniversalDashboardCLI.exe
BUILD_INFO.json
SHA256SUMS.txt
```

Intentional non-master releases are also marked prerelease.

### Optional signing

`python scripts\build_release.py --sign` signs the portable GUI/CLI before installer construction, signs the final setup afterward, verifies Authenticode signatures, and only then generates the final checksum manifest. Certificate secrets remain outside the repository.

Unsigned releases still function, but Windows may show Unknown Publisher/SmartScreen warnings.

## Release-tooling verification history

The release work was subjected to the same audit -> repair -> rerun discipline as the runtime.

The final release-tooling contract passed **21/21** pure tests before the exact tested blobs were committed. The committed core/test blobs were reread afterward; `scripts/release_common.py` is `11ffd9de043eae50158d2ca4def81bbb4654178e` and `tests/test_release_tooling.py` is `5486bb8ab56668ef25fe26287568e83b40c190b0`.

The release-specific adversarial passes found and repaired:

1. x64 install mode did not by itself guarantee a 64-bit setup loader; `SetupArchitecture=x64` plus PE validation now does.
2. semantic prerelease text was initially used in an Inno numeric version field; numeric and text product versions are separated.
3. version-only stale-artifact detection could not prove binaries came from the release commit; exact Git commit and clean-tree provenance are now recorded and enforced.
4. generating a checksum file without re-verifying it before upload could miss later artifact modification; publication now recomputes and verifies it.
5. temporary installer testing could have shared uninstall identity with a normal existing install; smoke testing now refuses to run when an existing install is detected.
6. stale portable binaries cannot be reused after VERSION/commit changes even with `--skip-app-build`.
7. a local release commit must match the pushed GitHub branch before publication, and reused remote tags are rejected.

## Final native installer acceptance required

Install current Inno Setup 7 once if necessary:

```powershell
winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
```

Then pull the final audit branch, ensure the worktree is clean, and run:

```powershell
python scripts\verify_windows.py --live-winget --installer
```

That command reruns the deterministic/native application gate, rebuilds source-bound AMD64 portable artifacts, compiles/verifies the true x64 installer, creates/verifies release hashes, smokes portable artifacts, installs the setup into a temporary directory, smokes the installed application, uninstalls it, and verifies cleanup.

## Current recommendation

The original reliability audit remains **PASS** and its native application evidence remains valid.

The release/installer implementation is complete and has passed its pure integrity contract. The only remaining evidence boundary is executing the current installer pipeline on Windows.

**If `python scripts\verify_windows.py --live-winget --installer` passes, the installer/release tranche can be marked accepted and the branch is ready to merge.**

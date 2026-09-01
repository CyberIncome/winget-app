# Windows x64 Release Guide

Winget Universal Dashboard uses a fully local release pipeline. GitHub Actions are not required.

## Release artifacts

A complete release produces:

- `dist\WingetUniversalDashboard-Setup-x64.exe` — recommended true AMD64/x64 Windows installer;
- `dist\WingetUniversalDashboard.exe` — portable GUI executable;
- `dist\WingetUniversalDashboardCLI.exe` — portable CLI executable;
- `dist\BUILD_INFO.json` — exact source version/commit and clean-tree provenance;
- `dist\SHA256SUMS.txt` — SHA-256 hashes for the installer, portable executables, and build identity.

The installer is built with Inno Setup 7 and installs per-user to:

`%LOCALAPPDATA%\Programs\WingetUniversalDashboard`

It creates a Start Menu shortcut, offers an optional desktop shortcut, includes the CLI executable and build identity, supports upgrade-over-existing-version behavior through a stable `AppId`, and registers a normal Windows uninstaller. User configuration under `%APPDATA%\WingetUniversalDashboard` and credentials stored by Windows keyring are outside the install directory and survive application upgrades/uninstall.

## Prerequisites

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Install current 64-bit Inno Setup 7:

```powershell
winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
```

The build script also accepts an explicit compiler path:

```powershell
$env:INNO_SETUP_COMPILER = 'C:\Program Files\Inno Setup 7\ISCC.exe'
```

The installer builder verifies that the selected compiler is Inno Setup 7 and verifies the resulting setup executable is AMD64 (`0x8664`).

## Versioning

`VERSION` is the single release version source. The initial release is `1.0.0`.

Use semantic versions such as `1.1.0`, `1.1.1`, `2.0.0`, or prereleases such as `2.0.0-rc.1`. Windows numeric version resources use the matching four-part numeric form (for example `2.0.0.0`) while the human-readable semantic version is retained in product metadata.

Change `VERSION`, commit it, and build only after the worktree is clean. A semantic prerelease is automatically published as a GitHub prerelease.

## Source identity and release integrity

Portable builds write `dist\BUILD_INFO.json` containing:

- the semantic `VERSION`;
- the exact Git commit SHA;
- whether the build worktree was dirty.

A complete release requires a **clean** worktree. Installer creation and GitHub publishing refuse artifacts unless `BUILD_INFO.json` matches the exact current version and commit and records `dirty: false`.

`SHA256SUMS.txt` covers:

- `WingetUniversalDashboard-Setup-x64.exe`;
- `WingetUniversalDashboard.exe`;
- `WingetUniversalDashboardCLI.exe`;
- `BUILD_INFO.json`.

The publisher recomputes and verifies those hashes before upload. This prevents stale binaries, a changed installer, or a modified provenance file from being published under a valid tag.

## Build a complete release

From a clean checkout:

```powershell
python scripts\build_release.py
```

This rebuilds the PyInstaller GUI/CLI executables, verifies they are AMD64 PE files, records their source identity, compiles a true x64 Inno Setup 7 installer, verifies that installer is also AMD64, and writes/verifies `SHA256SUMS.txt`.

To reuse already-built GUI/CLI files:

```powershell
python scripts\build_release.py --skip-app-build
```

That option is deliberately strict: it works only when `BUILD_INFO.json` proves the existing executables were built from the exact same clean `VERSION` and Git commit.

## Installer acceptance

For the full acceptance gate including a fresh release build and temporary install/uninstall:

```powershell
python scripts\verify_windows.py --live-winget --installer
```

`--installer` supersedes `--build`: it builds the complete release bundle, smokes the portable artifacts, then silently installs, launches, and uninstalls the setup executable.

The installer smoke uses a temporary installation directory. To avoid altering an existing normal installation's Inno uninstall registration, the smoke **refuses to run** if it detects an existing Winget Universal Dashboard install directory or matching HKCU uninstall entry.

## Optional Authenticode signing

Unsigned builds work, but Windows may display Unknown Publisher or SmartScreen reputation warnings.

If a suitable Authenticode certificate is installed in the Windows certificate store:

```powershell
$env:WUD_SIGN_CERT_SHA1 = 'YOUR_CERTIFICATE_THUMBPRINT'
```

Optional overrides:

```powershell
$env:SIGNTOOL_EXE = 'C:\Program Files (x86)\Windows Kits\10\bin\<version>\x64\signtool.exe'
$env:WUD_TIMESTAMP_URL = 'http://timestamp.digicert.com'
```

Then:

```powershell
python scripts\build_release.py --sign
```

The GUI and CLI are signed before installer creation; the completed installer is signed afterward. The final checksum manifest is generated after signing. Each signature is verified with `signtool verify /pa`.

Never commit private keys, PFX passwords, certificate exports, or signing secrets.

## GitHub Release publishing

Publishing is local and uses GitHub CLI rather than Actions.

Authenticate once if needed:

```powershell
gh auth login
```

For a normal release, first merge the accepted PR into `master`, pull `master`, ensure it is clean and pushed, then run the complete build/acceptance gate from that exact commit.

Create a **draft** GitHub Release:

```powershell
python scripts\publish_release.py
```

The publisher refuses:

- a dirty worktree;
- non-`master` branches unless `--allow-non-master` is explicit;
- a local branch whose HEAD differs from its pushed `origin/<branch>`;
- artifacts whose `BUILD_INFO.json` version/commit does not exactly match HEAD;
- checksum mismatches;
- non-AMD64 executables;
- a version tag that already exists remotely;
- a GitHub Release with the same version.

A non-`master` release or semantic prerelease is always marked as a prerelease. By default the release itself is still created as a **draft**.

After inspecting the draft/assets, publish it in GitHub's UI or create a public release directly:

```powershell
python scripts\publish_release.py --publish
```

The script creates `v<VERSION>` targeting the exact pushed commit and uploads the setup executable, portable GUI/CLI executables, `BUILD_INFO.json`, and `SHA256SUMS.txt`.
